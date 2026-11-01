# -*- coding: utf-8 -*-
"""
obk.py — 象棋开局库查询工具
用法:
    python obk.py                     # 查询初始局面
    python obk.py "<FEN>"             # 查询指定 FEN 局面
    python obk.py --key <vkey>        # 直接用 vkey 查询
    python obk.py --demo              # 用 bhobk.c 里的演示 key 查询
"""
import sqlite3, struct, sys, io
from zobrist_table import ZT, ZP

sys.stdout.reconfigure(encoding="utf-8")

DB = "test.obk"
START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

# FEN 字母 -> Zobrist 棋子编号(0-13)
# 红: 帅0 仕1 相2 马3 车4 炮5 兵6; 黑: 将7 士8 象9 马10 车11 炮12 卒13
CHESS = {'K':0,'A':1,'B':2,'N':3,'R':4,'C':5,'P':6,
         'k':7,'a':8,'b':9,'n':10,'r':11,'c':12,'p':13}

def fen_to_board(fen):
    """返回 (棋盘dict: (row,col)->字母, 是否红方走子)。row 0 = 黑方底线, col 0 = 棋盘最左"""
    parts = fen.split()
    rows = parts[0].split("/")
    assert len(rows) == 10, "FEN 应有 10 行"
    board = {}
    for r, line in enumerate(rows):
        col = 0
        for ch in line:
            if ch.isdigit():
                col += int(ch)
            else:
                board[(r, col)] = ch
                col += 1
        assert col == 9, "每行应有 9 列"
    red_to_move = (len(parts) < 2 or parts[1] != 'b')   # 缺省/'w' 都视为红走
    return board, red_to_move

def board_to_key(board, red_to_move):
    """按文档约定计算 Zobrist 哈希: square = ((row+3)<<4) | (col+3)"""
    key = 0
    for (r, c), ch in board.items():
        square = ((r + 3) << 4) | (c + 3)
        key ^= ZT[CHESS[ch]][square]
    if red_to_move:
        key ^= ZP
    return key

def query_book(key):
    """查询开局库，兼容 INTEGER 与 REAL 位模式两种存储形态"""
    con = sqlite3.connect(DB)
    cur = con.cursor()
    if key < (1 << 63):
        rows = cur.execute(
            "SELECT vmove,vscore,vwin,vdraw,vlost,vvalid,vmemo FROM bhobk WHERE vkey=?",
            (key,)).fetchall()
    else:
        d = struct.unpack('<d', struct.pack('<Q', key))[0]
        rows = cur.execute(
            "SELECT vmove,vscore,vwin,vdraw,vlost,vvalid,vmemo FROM bhobk WHERE vkey=?",
            (d,)).fetchall()
    con.close()
    return rows

# ---------- 着法翻译 ----------
RED_NAME   = {'K':'帅','R':'车','C':'炮','N':'马','B':'相','A':'仕','P':'兵'}
BLK_NAME   = {'k':'将','r':'车','c':'炮','n':'马','b':'象','a':'士','p':'卒'}
CN_NUM = "一二三四五六七八九"

def iccs(r, c):
    """(row,col) -> ICCS 坐标, 如 h2（rank 0 = 红方底线）"""
    return chr(ord('a') + c) + str(9 - r)

def move_cn(board, red_to_move, mv):
    """把 move = from<<8|to 翻译成中文着法，如 炮二平五"""
    fr, fc = (mv >> 12) - 3, ((mv >> 8) & 0xF) - 3
    tr, tc = ((mv >> 4) & 0xF) - 3, (mv & 0xF) - 3
    ch = board.get((fr, fc))
    if ch is None:
        return f"<空格起子 {iccs(fr,fc)}-{iccs(tr,tc)}>"
    is_red = ch.isupper()
    name = (RED_NAME if is_red else BLK_NAME)[ch]

    def fword(c):                                   # 纵线号：红方从右往左(中文数字)，黑方从左往右(阿拉伯)
        n = (9 - c) if is_red else (c + 1)
        return CN_NUM[n - 1] if is_red else str(n)

    # 同纵线同名棋子 -> 前/后/中 区分（按进的方向排序，最前者为"前"）
    same = sorted([r for (r, c), p in board.items() if c == fc and p == ch],
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

    if tr == fr:                                    # 平
        return prefix + "平" + fword(tc)
    forward = (tr < fr) if is_red else (tr > fr)
    verb = "进" if forward else "退"
    if ch.upper() in ('N', 'B', 'A'):               # 马相象仕：记目标纵线
        return prefix + verb + fword(tc)
    steps = abs(tr - fr)                            # 车炮帅将兵卒：记步数
    step_word = CN_NUM[steps - 1] if is_red else str(steps)
    return prefix + verb + step_word

# ---------- 主流程 ----------
def show(fen=None, key=None):
    if fen is not None:
        board, red_to_move = fen_to_board(fen)
        key = board_to_key(board, red_to_move)
        print(f"FEN: {fen}")
        print(f"走子方: {'红' if red_to_move else '黑'}")
    else:
        board, red_to_move = None, True
    print(f"vkey: {key}")
    rows = query_book(key)
    print(f"命中 {len(rows)} 条开局库着法:\n")
    if not rows:
        print("  (库中无此局面)")
        return
    print(f"  {'着法':<8}{'ICCS':<10}{'评分':>5} {'胜':>4} {'和':>4} {'负':>4} {'有效':>4}  备注")
    for mv, score, w, d, l, valid, memo in sorted(rows, key=lambda r: -r[1]):
        if board is not None:
            cn = move_cn(board, red_to_move, mv)
            fr, to = ((mv >> 8) & 0xFF), (mv & 0xFF)
            ic = iccs((fr >> 4) - 3, (fr & 0xF) - 3) + "-" + iccs((to >> 4) - 3, (to & 0xF) - 3)
        else:
            cn, ic = f"<move={mv}>", ""
        m = ""
        if memo:
            m = memo.decode("gbk", errors="replace") if isinstance(memo, bytes) else str(memo)
        print(f"  {cn:<8}{ic:<10}{score:>5} {w:>4} {d:>4} {l:>4} {valid:>4}  {m}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        show(fen=START_FEN)
    elif args[0] == "--key":
        show(key=int(args[1]))
    elif args[0] == "--demo":
        show(key=15265892774299731920)
    else:
        show(fen=" ".join(args))
