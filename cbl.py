"""CCBridge3 CBL/CBR 解析器，仅使用 Python 标准库。

负责读取棋库头、棋谱信息、90 字节棋盘、Unicode 注解以及主变/变着树。

Binary layout adapted from walker8088/cchess src/cchess/read_cbr.py (GPL-3.0+),
https://github.com/walker8088/cchess, and modified on 2026-11-03 to provide a
standalone data model, bounded reads, and malformed-input diagnostics.
"""
import struct
from dataclasses import dataclass, field
from pathlib import Path

CBL_MAGIC = b"CCBridgeLibrary\x00"
CBR_MAGIC = b"CCBridge Record\x00"
CBL_HEADER_SIZE = 576
CBL_RECORD_SIZE = 4096
CBR_HEADER = struct.Struct(
    "<16s164s128s384s64s320s64s160s64s712sB35sB3sH2s90si")
CBR_MOVE_SIZE = 4
CBL_INDEX_OFFSETS = (
    (128, 101952),
    (256, 137280),
    (384, 151080),
    (512, 207936),
)
DEFAULT_CBL_OFFSET = 349248
PIECES = {
    0x11: "R", 0x12: "N", 0x13: "B", 0x14: "A", 0x15: "K", 0x16: "C", 0x17: "P",
    0x21: "r", 0x22: "n", 0x23: "b", 0x24: "a", 0x25: "k", 0x26: "c", 0x27: "p",
}


class CBLError(ValueError):
    pass


@dataclass
class CBLMove:
    source: int
    target: int
    annotation: str = ""
    children: list = field(default_factory=list)


@dataclass
class CBLGame:
    title: str
    event: str
    red: str
    black: str
    result: int
    red_first: bool
    board: bytes
    annotation: str
    moves: list
    source_offset: int = 0

    def cells(self):
        cells = []
        for index, value in enumerate(self.board):
            if value == 0:
                cells.append(".")
            elif value in PIECES:
                cells.append(PIECES[value])
            else:
                raise CBLError(
                    f"record at 0x{self.source_offset:x}: unknown piece 0x{value:02x} "
                    f"at board index {index}")
        return tuple(cells)


@dataclass
class CBLLibrary:
    name: str
    declared_count: int
    games: list


def decode_text(data):
    for index in range(0, len(data) - 1, 2):
        if data[index:index + 2] == b"\x00\x00":
            data = data[:index]
            break
    if len(data) % 2:
        data = data[:-1]
    return data.decode("utf-16le", errors="replace")


class CBRReader:
    def __init__(self, data, offset=0):
        self.data = data
        self.offset = offset
        self.position = offset + CBR_HEADER.size

    def read(self, size):
        if size < 0:
            raise CBLError(f"record at 0x{self.offset:x}: negative field length {size}")
        end = self.position + size
        if end > len(self.data):
            raise CBLError(f"record at 0x{self.offset:x}: truncated data")
        result = self.data[self.position:end]
        self.position = end
        return result

    def read_int32(self):
        return struct.unpack("<i", self.read(4))[0]

    def remaining(self):
        return len(self.data) - self.position

    def read_annotation(self):
        if not self.read_int32():
            return ""
        return decode_text(self.read(self.read_int32()))

    def read_moves(self):
        if self.remaining() == 0:
            return []
        step = self.read(CBR_MOVE_SIZE)
        if step == b"\x00\x00\x00\x00":
            return []
        mark, _reserved, source, target = step
        if source >= 90 or target >= 90:
            raise CBLError(
                f"record at 0x{self.offset:x}: move coordinates outside the board: "
                f"{source}-{target}")
        annotation = decode_text(self.read(self.read_int32())) if mark & 0x04 else ""
        move = CBLMove(source, target, annotation)
        if not mark & 0x01:
            move.children = self.read_moves()
        variations = self.read_moves() if mark & 0x02 else []
        return [move] + variations


def parse_cbr(data, offset=0):
    if offset < 0 or offset + CBR_HEADER.size > len(data):
        raise CBLError(f"record at 0x{offset:x}: truncated header")
    fields = CBR_HEADER.unpack_from(data, offset)
    if fields[0] != CBR_MAGIC:
        raise CBLError(f"record at 0x{offset:x}: invalid CCBridge Record signature")
    reader = CBRReader(data, offset)
    game = CBLGame(
        title=decode_text(fields[2]),
        event=decode_text(fields[4]),
        red=decode_text(fields[6]),
        black=decode_text(fields[8]),
        result=fields[10],
        red_first=fields[14] == 1,
        board=fields[16],
        annotation="",
        moves=[],
        source_offset=offset,
    )
    game.cells()
    game.annotation = reader.read_annotation()
    game.moves = reader.read_moves()
    return game


def cbl_data_offset(declared_count):
    for maximum, offset in CBL_INDEX_OFFSETS:
        if declared_count <= maximum:
            return offset
    return DEFAULT_CBL_OFFSET


def parse_cbl(data):
    if len(data) < CBL_HEADER_SIZE:
        raise CBLError("truncated CBL header")
    magic, _reserved, declared_count, raw_name = struct.unpack_from(
        "<16s44si512s", data)
    if magic != CBL_MAGIC:
        raise CBLError("unsupported CBL signature; expected CCBridgeLibrary")
    if declared_count < 0:
        raise CBLError(f"negative CBL declared count {declared_count}")
    data_start = cbl_data_offset(declared_count)
    if data_start > len(data):
        raise CBLError("CBL data offset is beyond end of file")
    first_record = data.find(CBR_MAGIC, data_start)
    if first_record < 0:
        return CBLLibrary(decode_text(raw_name), declared_count, [])
    if (len(data) - first_record) % CBL_RECORD_SIZE:
        raise CBLError("CBL record area is not a multiple of 4096 bytes")
    games = []
    for offset in range(first_record, len(data), CBL_RECORD_SIZE):
        if data[offset:offset + len(CBR_MAGIC)] == CBR_MAGIC:
            games.append(parse_cbr(data, offset))
    return CBLLibrary(decode_text(raw_name), declared_count, games)


def read_cbl(path):
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise CBLError(f"{path}: cannot read CBL: {error}") from error
    try:
        return parse_cbl(data)
    except CBLError as error:
        raise CBLError(f"{path}: {error}") from error
