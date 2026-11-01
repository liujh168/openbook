#!/usr/bin/env python3
"""Convert the current SQLite OBK format to jqxq's 16-byte book format.

Conversion algorithms are derived from jqxq's tests/make_book.py and
xiangqi_oracle.py. jqxq is licensed under GPL-3.0+; see LICENSE.
"""
import argparse
import os
import re
import sqlite3
import struct
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from zobrist_table import ZT, ZP

ROOT = Path(__file__).resolve().parent
MASK64 = (1 << 64) - 1
ENTRY = struct.Struct("<QHHI")
START = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
OBK_TYPES = {"k": 0, "a": 1, "b": 2, "n": 3, "r": 4, "c": 5, "p": 6}
JQXQ_TYPES = {"p": 1, "b": 2, "a": 3, "c": 4, "n": 5, "r": 6, "k": 7}


class BookError(ValueError):
    pass


def color(piece):
    return 0 if piece.isupper() else 1


def palace(x, y, side):
    return 3 <= x <= 5 and (7 <= y <= 9 if side == 0 else 0 <= y <= 2)


@dataclass(frozen=True)
class Board:
    cells: tuple
    side: int = 0

    @classmethod
    def from_fen(cls, fen):
        fields = fen.split()
        rows = fields[0].split("/")
        if len(rows) != 10 or len(fields) < 2 or fields[1] not in ("r", "w", "b"):
            raise BookError("invalid FEN")
        cells = []
        for row in rows:
            line = []
            for char in row:
                if char in "123456789":
                    line.extend("." * int(char))
                elif char in "rnbakcpRNBAKCP":
                    line.append(char)
                else:
                    raise BookError("invalid piece " + char)
            if len(line) != 9:
                raise BookError("invalid rank width")
            cells.extend(line)
        if cells.count("k") != 1 or cells.count("K") != 1:
            raise BookError("expected two kings")
        return cls(tuple(cells), int(fields[1] == "b"))

    def reaches(self, src, dst):
        piece, target = self.cells[src], self.cells[dst]
        if piece == "." or src == dst:
            return False
        side, kind = color(piece), piece.lower()
        x, y, xx, yy = src % 9, src // 9, dst % 9, dst // 9
        dx, dy = xx - x, yy - y
        ax, ay = abs(dx), abs(dy)
        if kind in ("r", "c") or (kind == "k" and target.lower() == "k" and x == xx):
            if dx and dy:
                return False
            step = (1 if dx > 0 else -1) if dx else (9 if dy > 0 else -9)
            screens = sum(self.cells[square] != "." for square in range(src + step, dst, step))
            return screens == (1 if kind == "c" and target != "." else 0)
        if kind == "n":
            if ax * ay != 2:
                return False
            leg = src + ((1 if dx > 0 else -1) if ax == 2 else (9 if dy > 0 else -9))
            return self.cells[leg] == "."
        if kind == "b":
            return (ax == ay == 2 and (yy >= 5 if side == 0 else yy <= 4)
                    and self.cells[(src + dst) // 2] == ".")
        if kind == "a":
            return ax == ay == 1 and palace(xx, yy, side)
        if kind == "k":
            return ax + ay == 1 and palace(xx, yy, side)
        if kind == "p":
            return ((dx == 0 and dy == (-1 if side == 0 else 1))
                    or (dy == 0 and ax == 1 and (y <= 4 if side == 0 else y >= 5)))
        return False

    def in_check(self, side=None):
        side = self.side if side is None else side
        target = self.cells.index("K" if side == 0 else "k")
        return any(piece != "." and color(piece) != side
                   and self.reaches(square, target)
                   for square, piece in enumerate(self.cells))

    def apply(self, move):
        src, dst = move
        cells = list(self.cells)
        cells[dst], cells[src] = cells[src], "."
        return Board(tuple(cells), 1 - self.side)

    def legal(self, move):
        src, dst = move
        piece, target = self.cells[src], self.cells[dst]
        return (piece != "." and color(piece) == self.side and target.lower() != "k"
                and (target == "." or color(target) != self.side)
                and self.reaches(src, dst) and not self.apply(move).in_check(self.side))


@dataclass
class Stats:
    sqlite_records: int = 0
    observations: int = 0
    disabled_records: int = 0
    zero_weight_records: int = 0
    unmatched_records: int = 0
    unmatched_examples: list = field(default_factory=list)


class BookBuilder:
    def __init__(self):
        self.counts = Counter()
        self.saturations = 0

    def add(self, key, move, weight=1):
        if not 0 <= key <= MASK64 or not 0 <= move <= 0xFFFF:
            raise BookError("book key or move is outside its unsigned range")
        if weight < 0:
            raise BookError("book weight cannot be negative")
        if weight:
            pair = (key, move)
            total = self.counts[pair] + int(weight)
            self.saturations += total > 65535
            self.counts[pair] = min(65535, total)

    def entries(self):
        return [(key, move, count, 0)
                for (key, move), count in sorted(self.counts.items())]

    def serialize(self):
        return b"".join(ENTRY.pack(*entry) for entry in self.entries())


def load_jqxq_randoms(path=None):
    path = Path(path) if path is not None else ROOT / "jqxq_zobrist.h"
    text = path.read_text(encoding="utf-8")
    values = [int(value, 16) for value in
              re.findall(r"0x([0-9a-fA-F]{1,16})ULL\b", text)]
    if len(values) != 3842:
        raise BookError(f"{path}: expected 3842 Zobrist constants, found {len(values)}")
    return values


def obk_key(board):
    key = 0
    for index, piece in enumerate(board.cells):
        if piece != ".":
            row, col = divmod(index, 9)
            square = ((row + 3) << 4) | (col + 3)
            kind = OBK_TYPES[piece.lower()] + (7 if piece.islower() else 0)
            key ^= ZT[kind][square]
    if board.side == 0:
        key ^= ZP
    return key


def jqxq_key(board, randoms):
    if len(randoms) != 3842:
        raise BookError("jqxq Zobrist table must contain 3842 constants")
    key = 0
    for index, piece in enumerate(board.cells):
        if piece != ".":
            row, col = divmod(index, 9)
            square = ((row + 3) << 4) | (col + 3)
            flat = (JQXQ_TYPES[piece.lower()] + color(piece) * 7) * 256 + square
            key ^= randoms[flat]
    if board.side == 1:
        key ^= randoms[3840]
    return key


def decode_obk_move(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF:
        raise BookError(f"move must be a 16-bit integer, got {value!r}")
    src_row, src_col = ((value >> 12) & 15) - 3, ((value >> 8) & 15) - 3
    dst_row, dst_col = ((value >> 4) & 15) - 3, (value & 15) - 3
    if not (0 <= src_row < 10 and 0 <= dst_row < 10
            and 0 <= src_col < 9 and 0 <= dst_col < 9):
        raise BookError(f"move 0x{value:04x} has coordinates outside the board")
    return src_row * 9 + src_col, dst_row * 9 + dst_col


def encoded_move(move):
    src, dst = move
    return ((((src // 9 + 3) * 16 + src % 9 + 3) << 8)
            | ((dst // 9 + 3) * 16 + dst % 9 + 3))


def uint64_sql_value(value, context):
    if isinstance(value, bool):
        raise BookError(f"{context}: boolean is not a 64-bit key")
    if isinstance(value, int):
        return value & MASK64
    if isinstance(value, float):
        return struct.unpack("<Q", struct.pack("<d", value))[0]
    raise BookError(f"{context}: vkey must be SQLite INTEGER or FLOAT bit pattern")


def record_weight(win, draw, lost, context):
    values = []
    for name, value in (("win", win), ("draw", draw), ("lost", lost)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BookError(f"{context}: {name} count must be a nonnegative integer")
        values.append(value)
    return sum(values)


def sqlite_readonly(path):
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise BookError(f"{path}: cannot open SQLite input read-only: {error}")


def columns(connection, table):
    try:
        rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    except sqlite3.Error as error:
        raise BookError(f"cannot inspect SQLite table {table}: {error}")
    return {row[1].lower(): row[1] for row in rows}


def import_obk(path, builder, randoms, max_plies=None, stats=None):
    stats = stats if stats is not None else Stats()
    if max_plies is not None and max_plies < 0:
        raise BookError("--max-plies must be nonnegative")
    connection = sqlite_readonly(path)
    records = {}
    null_key_rowids = set()
    total = 0
    try:
        names = columns(connection, "bhobk")
        required = {"vkey", "vmove", "vwin", "vdraw", "vlost", "vvalid"}
        if not required.issubset(names):
            missing = ", ".join(sorted(required - set(names)))
            raise BookError(f"{path}: bhobk lacks required columns: {missing}")
        query = 'SELECT rowid,"%s","%s","%s","%s","%s","%s" FROM bhobk ORDER BY rowid' % tuple(
            names[name] for name in ("vkey", "vmove", "vwin", "vdraw", "vlost", "vvalid"))
        for rowid, vkey, move, win, draw, lost, valid in connection.execute(query):
            total += 1
            context = f"{path}:bhobk rowid {rowid}"
            if vkey is None:
                null_key_rowids.add(rowid)
                continue
            key = uint64_sql_value(vkey, context)
            weight = record_weight(win, draw, lost, context)
            records.setdefault(key, []).append((rowid, move, weight, valid))
    except sqlite3.Error as error:
        raise BookError(f"{path}: invalid OBK database: {error}")
    finally:
        connection.close()

    stats.sqlite_records += total
    matched = set()
    pending = [(Board.from_fen(START), 0)]
    seen = {}
    while pending:
        board, depth = pending.pop()
        if max_plies is not None and depth >= max_plies:
            continue
        identity = (board.cells, board.side)
        if identity in seen and seen[identity] <= depth:
            continue
        seen[identity] = depth
        group = records.get(obk_key(board), [])
        for rowid, raw_move, weight, valid in sorted(group):
            matched.add(rowid)
            context = f"{path}:bhobk rowid {rowid}"
            if not isinstance(valid, int) or isinstance(valid, bool) or valid != 1:
                stats.disabled_records += 1
                continue
            try:
                move = decode_obk_move(raw_move)
                if not board.legal(move):
                    raise BookError("move is not legal in the matched position")
            except BookError as error:
                raise BookError(f"{context}: {error}")
            if weight:
                builder.add(jqxq_key(board, randoms), encoded_move(move), weight)
                stats.observations += 1
            else:
                stats.zero_weight_records += 1
            if max_plies is None or depth < max_plies:
                pending.append((board.apply(move), depth + 1))

    all_rowids = ({rowid for group in records.values() for rowid, _, _, _ in group}
                  | null_key_rowids)
    unmatched = sorted(all_rowids - matched)
    stats.unmatched_records += len(unmatched)
    stats.unmatched_examples.extend(f"{path}:bhobk rowid {rowid}" for rowid in unmatched[:20])
    return stats


def verify_book(source):
    if isinstance(source, (str, os.PathLike)):
        path = Path(source)
        with path.open("rb") as stream:
            data = stream.read()
        name = str(path)
    else:
        data = bytes(source)
        name = "<bytes>"
    if len(data) % ENTRY.size:
        raise BookError(f"{name}: size {len(data)} is not a multiple of 16")
    previous = None
    keys = set()
    for offset in range(0, len(data), ENTRY.size):
        key, move, count, learn = ENTRY.unpack_from(data, offset)
        pair = (key, move)
        if previous is not None and pair <= previous:
            raise BookError(f"{name}: entries are not strictly key/move sorted at byte {offset}")
        if learn != 0:
            raise BookError(f"{name}: nonzero learn field at byte {offset}")
        if count == 0:
            raise BookError(f"{name}: zero count at byte {offset}")
        previous = pair
        keys.add(key)
    return {"entries": len(data) // ENTRY.size, "positions": len(keys), "bytes": len(data)}


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def load_book(path, builder):
    summary = verify_book(path)
    data = Path(path).read_bytes()
    for offset in range(0, len(data), ENTRY.size):
        key, move, count, _ = ENTRY.unpack_from(data, offset)
        builder.add(key, move, count)
    return summary


def make_book(input_path, output_path, max_plies=None, merge=False):
    randoms = load_jqxq_randoms()
    builder = BookBuilder()
    if merge:
        load_book(output_path, builder)
    stats = import_obk(input_path, builder, randoms, max_plies=max_plies)
    data = builder.serialize()
    summary = verify_book(data)
    atomic_write(output_path, data)
    return builder, stats, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="将当前 SQLite OBK 转换为 jqxq book.bin")
    parser.add_argument("input", nargs="?", default="test.obk", help="源 OBK 文件")
    parser.add_argument("-o", "--output", default="book.bin", help="目标二进制库")
    parser.add_argument("--max-plies", type=int, help="最大遍历半回合数，默认不限")
    parser.add_argument("--merge", action="store_true", help="读取并合并已有目标库")
    parser.add_argument("--verify", metavar="FILE", help="只校验已有二进制库")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            summary = verify_book(args.verify)
            print("校验通过: entries={entries} positions={positions} bytes={bytes}".format(**summary))
            return 0
        builder, stats, summary = make_book(
            args.input, args.output, args.max_plies, merge=args.merge)
        print(f"源记录: {stats.sqlite_records}")
        print(f"输出记录: {summary['entries']}")
        print(f"输出局面: {summary['positions']}")
        print(f"可达禁用记录: {stats.disabled_records}")
        print(f"零权重记录: {stats.zero_weight_records}")
        print(f"不可达记录: {stats.unmatched_records}")
        print(f"权重饱和次数: {builder.saturations}")
        if stats.unmatched_examples:
            print("不可达示例: " + ", ".join(stats.unmatched_examples))
        print(f"已生成: {args.output} ({summary['bytes']} 字节)")
        return 0
    except (BookError, OSError, sqlite3.Error) as error:
        print(f"转换失败: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
