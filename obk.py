# -*- coding: utf-8 -*-
"""SQLite OBK 与 CCBridge3 CBL 查询及分叉跟踪工具。

提供 FEN/key 查询、库校验、中文/ICCS 着法解析及批量/交互跟踪。
"""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import sys

from cbl import CBL_MAGIC, CBLError, read_cbl
from convert_obk import Board
from xqgen import apply, gen_moves
from zobrist_table import ZT, ZP

DB = "test.obk"
START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
MASK64 = (1 << 64) - 1

CHESS = {'K': 0, 'A': 1, 'B': 2, 'N': 3, 'R': 4, 'C': 5, 'P': 6,
         'k': 7, 'a': 8, 'b': 9, 'n': 10, 'r': 11, 'c': 12, 'p': 13}
RED_NAME = {'K': '帅', 'R': '车', 'C': '炮', 'N': '马', 'B': '相', 'A': '仕', 'P': '兵'}
BLK_NAME = {'k': '将', 'r': '车', 'c': '炮', 'n': '马', 'b': '象', 'a': '士', 'p': '卒'}
DISPLAY_NAME = {'K': '帅', 'A': '仕', 'B': '相', 'N': '马', 'R': '车', 'C': '炮', 'P': '兵',
                'k': '將', 'a': '士', 'b': '象', 'n': '馬', 'r': '車', 'c': '砲', 'p': '卒'}
CN_NUM = "一二三四五六七八九"
REQUIRED_COLUMNS = "vkey,vmove,vscore,vwin,vdraw,vlost,vvalid,vmemo"


class ObkError(ValueError):
    pass


def fen_to_board(fen):
    """返回 (棋盘字典, 是否红方走子)，row 0 为黑方底线。"""
    parts = fen.split()
    if not parts:
        raise ObkError("FEN 不能为空")
    rows = parts[0].split("/")
    if len(rows) != 10:
        raise ObkError("FEN 应有 10 行")
    board = {}
    for r, line in enumerate(rows):
        col = 0
        for ch in line:
            if ch in "123456789":
                col += int(ch)
            else:
                if ch not in CHESS:
                    raise ObkError(f"FEN 含未知棋子 {ch!r}")
                if col > 8:
                    raise ObkError("FEN 每行应有 9 列")
                board[(r, col)] = ch
                col += 1
        if col != 9:
            raise ObkError("FEN 每行应有 9 列")
    red_to_move = len(parts) < 2 or parts[1] != 'b'
    return board, red_to_move


def board_to_key(board, red_to_move):
    """按原始 OBK 约定计算 Zobrist 局面键。"""
    key = 0
    for (r, c), ch in board.items():
        square = ((r + 3) << 4) | (c + 3)
        key ^= ZT[CHESS[ch]][square]
    if red_to_move:
        key ^= ZP
    return key


def open_book(db_path=DB):
    path = Path(db_path)
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise ObkError(f"无法打开 {db_path}: {error}") from error


def query_book(key, db_path=DB):
    """查询 OBK 原始记录或 CBL 聚合着法，统一为七字段行。"""
    if isinstance(key, bool) or not isinstance(key, int) or not 0 <= key <= MASK64:
        raise ObkError(f"无效的 vkey: {key}")
    if is_cbl_book(db_path):
        return get_cbl_book(db_path).query(key)
    value = key
    if key >= (1 << 63):
        value = struct.unpack('<d', struct.pack('<Q', key))[0]
    try:
        with closing(open_book(db_path)) as connection:
            return connection.execute(
                f"SELECT {REQUIRED_COLUMNS.split(',', 1)[1]} FROM bhobk WHERE vkey=?",
                (value,)).fetchall()
    except sqlite3.Error as error:
        raise ObkError(f"查询 {db_path} 失败: {error}") from error


def check_book(db_path=DB):
    """检查 OBK 完整性，或解析 CBL 并验证全部可回放分支。"""
    if is_cbl_book(db_path):
        return get_cbl_book(db_path)
    try:
        with closing(open_book(db_path)) as connection:
            rows = connection.execute("PRAGMA quick_check;").fetchall()
            if len(rows) != 1 or not rows[0] or rows[0][0] != "ok":
                detail = rows[0][0] if rows and rows[0] else "quick_check 未返回结果"
                raise ObkError(str(detail))
            connection.execute(f"SELECT {REQUIRED_COLUMNS} FROM bhobk LIMIT 0;").fetchall()
    except sqlite3.Error as error:
        raise ObkError(str(error)) from error


def iccs(r, c):
    return chr(ord('a') + c) + str(9 - r)


def decode_move(mv):
    if isinstance(mv, bool) or not isinstance(mv, int) or not 0 <= mv <= 0xFFFF:
        raise ObkError(f"无效的走法码: {mv}")
    fr, fc = (mv >> 12) - 3, ((mv >> 8) & 0xF) - 3
    tr, tc = ((mv >> 4) & 0xF) - 3, (mv & 0xF) - 3
    if not (0 <= fr < 10 and 0 <= tr < 10 and 0 <= fc < 9 and 0 <= tc < 9):
        raise ObkError(f"走法码超出棋盘: {mv}")
    return fr, fc, tr, tc


def encode_move(move):
    fr, fc, tr, tc = move
    if not (0 <= fr < 10 and 0 <= tr < 10 and 0 <= fc < 9 and 0 <= tc < 9):
        raise ObkError(f"走法坐标超出棋盘: {move}")
    source = ((fr + 3) << 4) | (fc + 3)
    target = ((tr + 3) << 4) | (tc + 3)
    return (source << 8) | target


def move_iccs(mv):
    fr, fc, tr, tc = decode_move(mv)
    return f"{iccs(fr, fc)}-{iccs(tr, tc)}"


def apply_move(board, mv):
    return apply(board, decode_move(mv))


class CBLBook:
    def __init__(self, db_path):
        self.path = Path(db_path)
        self.entries = {}
        self.game_count = 0
        self.move_count = 0
        self.skipped_branches = 0
        self.skipped_moves = 0
        try:
            library = read_cbl(self.path)
        except CBLError as error:
            raise ObkError(str(error)) from error
        self.name = library.name
        self.game_count = len(library.games)
        for index, game in enumerate(library.games, 1):
            try:
                board = Board(game.cells(), 0 if game.red_first else 1)
                board.in_check(0)
                board.in_check(1)
            except (CBLError, ValueError) as error:
                raise ObkError(f"{self.path}: 第 {index} 局初始棋盘无效: {error}") from error
            self._index_moves(game.moves, board)

    @staticmethod
    def _key(board):
        cells = {(index // 9, index % 9): piece
                 for index, piece in enumerate(board.cells) if piece != "."}
        return board_to_key(cells, board.side == 0)

    @staticmethod
    def _subtree_size(moves):
        return sum(1 + CBLBook._subtree_size(move.children) for move in moves)

    def _index_moves(self, moves, board):
        for cbl_move in moves:
            source, target = cbl_move.source, cbl_move.target
            piece = board.cells[source]
            move_board = Board(board.cells, 0 if piece.isupper() else 1) if piece != "." else board
            if piece == "." or not move_board.legal((source, target)):
                self.skipped_branches += 1
                self.skipped_moves += 1 + self._subtree_size(cbl_move.children)
                continue
            move = (source // 9, source % 9, target // 9, target % 9)
            encoded = encode_move(move)
            entry = self.entries.setdefault(self._key(move_board), {}).setdefault(encoded, [0, []])
            entry[0] += 1
            self.move_count += 1
            if cbl_move.annotation and cbl_move.annotation not in entry[1]:
                entry[1].append(cbl_move.annotation)
            self._index_moves(cbl_move.children, move_board.apply((source, target)))

    def query(self, key):
        return [(mv, count, 0, 0, 0, 1, "\n".join(annotations))
                for mv, (count, annotations) in self.entries.get(key, {}).items()]


_CBL_CACHE = {}


def is_cbl_book(db_path):
    path = Path(db_path)
    if path.suffix.lower() == ".cbl":
        return True
    try:
        with path.open("rb") as stream:
            return stream.read(len(CBL_MAGIC)) == CBL_MAGIC
    except OSError:
        return False


def get_cbl_book(db_path):
    path = Path(db_path).resolve()
    try:
        stat = path.stat()
    except OSError as error:
        raise ObkError(f"无法打开 {db_path}: {error}") from error
    identity = (str(path), stat.st_mtime_ns, stat.st_size)
    if identity not in _CBL_CACHE:
        _CBL_CACHE[identity] = CBLBook(path)
    return _CBL_CACHE[identity]


def move_cn(board, red_to_move, mv):
    """把 mailbox 走法码翻译成中文着法，如 炮二平五。"""
    try:
        fr, fc, tr, tc = decode_move(mv)
    except ObkError:
        return f"<非法走法 {mv}>"
    ch = board.get((fr, fc))
    if ch is None:
        return f"<非法走法 {mv}>"
    is_red = ch.isupper()
    name = (RED_NAME if is_red else BLK_NAME)[ch]

    def fword(c):
        n = (9 - c) if is_red else (c + 1)
        return CN_NUM[n - 1] if is_red else str(n)

    same = sorted((r for (r, c), p in board.items() if c == fc and p == ch),
                  reverse=not is_red)
    if len(same) >= 2:
        idx = same.index(fr)
        if len(same) == 2:
            pos_word = "前" if idx == 0 else "后"
        elif len(same) == 3:
            pos_word = ["前", "中", "后"][idx]
        else:
            pos_word = ["前", "二", "三", "四", "五"][min(idx, 4)]
        prefix = pos_word + name
    else:
        prefix = name + fword(fc)

    if tr == fr:
        return prefix + "平" + fword(tc)
    forward = (tr < fr) if is_red else (tr > fr)
    verb = "进" if forward else "退"
    if ch.upper() in ('N', 'B', 'A'):
        return prefix + verb + fword(tc)
    steps = abs(tr - fr)
    step_word = CN_NUM[steps - 1] if is_red else str(steps)
    return prefix + verb + step_word


def parse_move(board, red_to_move, text):
    """把中文着法或 ICCS 解析为走法码，无法识别时返回 None。"""
    for move in gen_moves(board, red_to_move):
        mv = encode_move(move)
        if text == move_cn(board, red_to_move, mv) or text.lower() == move_iccs(mv).lower():
            return mv
    return None


def print_board(board):
    print("    a  b  c  d  e  f  g  h  i")
    for r in range(10):
        print(f" {9 - r}  ", end="")
        for c in range(9):
            print(f"{DISPLAY_NAME.get(board.get((r, c)), '＋')} ", end="")
        print()
        if r == 4:
            print("   ~~~~~~~~ 楚 河 漢 界 ~~~~~~~~")


def sorted_entries(rows):
    return sorted(rows, key=lambda row: -row[1])


def print_branches(board, rows, played=None):
    if not rows:
        return
    parts = []
    for index, row in enumerate(rows):
        if index == played:
            continue
        parts.append(f"{move_cn(board, True, row[0])}({row[1]}){'' if row[5] else '*'}")
        if len(parts) >= 8 and len(rows) > 9:
            parts.append("...")
            break
    print(f"   分叉({len(rows)}): " + " ".join(parts))


def find_entry(rows, mv):
    return next((index for index, row in enumerate(rows) if row[0] == mv), -1)


def play_step(board, red_to_move, step, text, out_of_book, db_path=DB):
    mv = parse_move(board, red_to_move, text)
    if mv is None:
        print(f"第 {step} 步: 无法识别着法 \"{text}\", 跟踪结束")
        return board, out_of_book, False
    key = board_to_key(board, red_to_move)
    rows = sorted_entries(query_book(key, db_path))
    index = find_entry(rows, mv)
    cn = move_cn(board, red_to_move, mv)
    ic = move_iccs(mv)
    side = "红" if red_to_move else "黑"

    if out_of_book:
        print(f"第 {step} 步 {side}: {cn} {ic}  [已出谱]")
    elif not rows:
        print(f"第 {step} 步 {side}: {cn} {ic}  [到边界] 当前局面不在开局库, 此后脱谱")
        out_of_book = True
    elif index >= 0:
        row = rows[index]
        if is_cbl_book(db_path):
            print(f"第 {step} 步 {side}: {cn} {ic}  [在谱] 次数{row[1]}")
        else:
            print(f"第 {step} 步 {side}: {cn} {ic}  [在谱] 评分{row[1]} "
                  f"胜{row[2]} 和{row[3]} 负{row[4]}{'' if row[5] else ' (被禁)'}")
        print_branches(board, rows, index)
    else:
        print(f"第 {step} 步 {side}: {cn} {ic}  [脱谱] 库中无此着法, 此后脱谱")
        print_branches(board, rows, -1)
        out_of_book = True
    new_board = apply_move(board, mv)
    print_board(new_board)
    return new_board, out_of_book, True


def play_mode(moves, db_path=DB, input_stream=None):
    board, red_to_move = fen_to_board(START_FEN)
    step = 1
    out_of_book = False
    print("=== 分叉跟踪(从初始局面) ===")
    print_board(board)

    if moves:
        for text in moves:
            board, out_of_book, ok = play_step(
                board, red_to_move, step, text, out_of_book, db_path)
            if not ok:
                return
            step += 1
            red_to_move = not red_to_move
        if not out_of_book:
            rows = sorted_entries(query_book(board_to_key(board, red_to_move), db_path))
            print(f"--- 当前轮到{'红' if red_to_move else '黑'}, ", end="")
            if rows:
                print_branches(board, rows, -1)
            else:
                print("分叉(0)")
        return

    stream = input_stream or sys.stdin
    history = []
    while True:
        rows = sorted_entries(query_book(board_to_key(board, red_to_move), db_path))
        print(f"第 {step} 步 {'红' if red_to_move else '黑'}走子"
              f"{' (已脱谱)' if out_of_book else ''} (b=回退 q=退出)")
        if not out_of_book:
            print_branches(board, rows, -1)
        print("> ", end="", flush=True)
        line = stream.readline()
        if not line:
            break
        text = line.strip()
        if not text or text in ("q", "quit"):
            break
        if text in ("b", "back"):
            if history:
                board, out_of_book = history.pop()
                red_to_move = not red_to_move
                step -= 1
                print(f"已回退到第 {step} 步 {'红' if red_to_move else '黑'}走子:")
                print_board(board)
            else:
                print("已经是初始局面, 无法回退")
            continue
        history.append((board, out_of_book))
        board, out_of_book, ok = play_step(
            board, red_to_move, step, text, out_of_book, db_path)
        if not ok:
            break
        step += 1
        red_to_move = not red_to_move


def show(fen=None, key=None, db_path=DB):
    cbl = is_cbl_book(db_path)
    if fen is not None:
        board, red_to_move = fen_to_board(fen)
        key = board_to_key(board, red_to_move)
        print(f"FEN: {fen}")
        print(f"走子方: {'红' if red_to_move else '黑'}")
        print_board(board)
    else:
        board, red_to_move = None, True
    print(f"vkey: {key}")
    if cbl:
        print(f"棋库: {get_cbl_book(db_path).name}")
    rows = query_book(key, db_path)
    print(f"命中 {len(rows)} 条开局库着法:\n")
    if not rows:
        print("  (库中无此局面)")
        return
    if cbl:
        print(f"  {'着法':<8}{'ICCS':<10}{'次数':>5}  备注")
    else:
        print(f"  {'着法':<8}{'ICCS':<10}{'评分':>5} {'胜':>4} {'和':>4} {'负':>4} {'有效':>4}  备注")
    for mv, score, w, d, l, valid, memo in sorted_entries(rows):
        if board is not None:
            cn = move_cn(board, red_to_move, mv)
            try:
                ic = move_iccs(mv)
            except ObkError:
                ic = ""
        else:
            cn, ic = f"<move={mv}>", ""
        m = ""
        if memo:
            m = memo.decode("gbk", errors="replace") if isinstance(memo, bytes) else str(memo)
        if cbl:
            print(f"  {cn:<8}{ic:<10}{score:>5}  {m}")
        else:
            print(f"  {cn:<8}{ic:<10}{score:>5} {w:>4} {d:>4} {l:>4} {valid:>4}  {m}")


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: 参数错误: {message}\n")


def build_parser():
    parser = ArgumentParser(
        description="OBK/CCBridge3 CBL 象棋开局库查询工具",
        epilog="着法支持中文或 ICCS 坐标(如 炮二平五、h2-e2)；交互模式支持 b=回退，空行/q=退出。")
    parser.add_argument("--db", metavar="文件", default=DB,
                        help=f"指定原始 OBK 或 CCBridge3 CBL(默认 {DB})")
    parser.add_argument("--check", action="store_true", help="检查开局库结构和可回放分支")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--key", metavar="vkey", help="直接按十进制 vkey 查询")
    modes.add_argument("--demo", action="store_true", help="OBK 查询高位 REAL 演示 key；CBL 查询初始局面")
    modes.add_argument("--play", nargs="*", metavar="着法", help="分叉跟踪；无着法时进入交互模式")
    parser.add_argument("fen", nargs="*", help="查询指定 FEN；缺省查询初始局面")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    has_query = args.key is not None or args.demo or args.play is not None or bool(args.fen)
    if args.check and has_query:
        parser.error("--check 不能与其他查询参数同时使用")
    if not args.check and args.fen and (args.key is not None or args.demo or args.play is not None):
        parser.error("FEN 不能与其他查询模式同时使用")
    if not has_query and not args.check:
        print("提示: 使用 -h 或 --help 查看命令行帮助。\n")

    try:
        if args.check:
            print(f"检查文件: {args.db}")
            try:
                book = check_book(args.db)
            except ObkError as error:
                print(f"检查结果: 不合法 ({error})")
                return 1
            print("检查结果: 合法")
            if is_cbl_book(args.db):
                print(f"CBL 棋谱: {book.game_count}, 合法着法: {book.move_count}, "
                      f"跳过分支: {book.skipped_branches}, 跳过非法着法: {book.skipped_moves}")
            else:
                print("SQLite 快速检查及 bhobk 表必需字段检查均通过。")
            return 0
        if args.play is not None:
            play_mode(args.play, args.db)
            return 0
        if args.demo:
            demo_key = (board_to_key(*fen_to_board(START_FEN)) if is_cbl_book(args.db)
                        else 15265892774299731920)
            show(key=demo_key, db_path=args.db)
            return 0
        if args.key is not None:
            try:
                key = int(args.key, 10)
            except ValueError as error:
                raise ObkError(f"无效的 vkey: {args.key}") from error
            show(key=key, db_path=args.db)
            return 0
        show(fen=" ".join(args.fen) if args.fen else START_FEN, db_path=args.db)
        return 0
    except (ObkError, OSError) as error:
        print(f"错误: {error}")
        return 1


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
