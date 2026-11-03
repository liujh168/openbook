"""CCBridge3 CBL 解析、转换与查询的单元及命令行测试。

以自包含二进制样本覆盖元数据、主变/变着、权重、深度限制及非法分支。
"""

import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cbl
import convert_obk as co


def run_obk(args, expected_code=0, input_text=None):
    result = subprocess.run(
        [sys.executable, str(ROOT / "obk.py"), *map(str, args)], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", timeout=30, input=input_text)
    if result.returncode != expected_code:
        raise AssertionError(f"命令退出码为 {result.returncode}，预期 {expected_code}\n{result.stdout}")
    return result.stdout


def fixed_text(text, size):
    return (text + "\x00").encode("utf-16le").ljust(size, b"\x00")[:size]


def standard_board():
    reverse = {piece: value for value, piece in cbl.PIECES.items()}
    return bytes(reverse.get(piece, 0) for piece in co.Board.from_fen(co.START).cells)


def move(source, target, mark=1, annotation=""):
    data = bytes((mark | (4 if annotation else 0), 0, source, target))
    if annotation:
        encoded = annotation.encode("utf-16le")
        data += struct.pack("<i", len(encoded)) + encoded
    return data


def make_cbr(moves, title="测试棋谱", annotation="", board=None, red_first=True):
    board = standard_board() if board is None else board
    header = cbl.CBR_HEADER.pack(
        cbl.CBR_MAGIC, b"", fixed_text(title, 128), b"", fixed_text("测试赛事", 64), b"",
        fixed_text("红方", 64), b"", fixed_text("黑方", 64), b"", 4,
        b"", 0, b"", 1 if red_first else 0, b"", board, 0)
    encoded = annotation.encode("utf-16le")
    initial = struct.pack("<i", 1 if annotation else 0)
    if annotation:
        initial += struct.pack("<i", len(encoded)) + encoded
    return header + initial + moves + b"\x00\x00\x00\x00"


def make_cbl(records, name="测试棋库"):
    header = struct.pack(
        "<16s44si512s", cbl.CBL_MAGIC, b"", 1, fixed_text(name, 512))
    data = header.ljust(cbl.cbl_data_offset(1), b"\x00")
    return data + b"".join(record.ljust(cbl.CBL_RECORD_SIZE, b"\x00") for record in records)


def branching_game():
    moves = (
        move(70, 67, mark=2, annotation="首着注解")
        + move(7, 24)
        + move(56, 47)
    )
    return make_cbr(moves, annotation="棋谱注解")


class CBLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.randoms = co.load_jqxq_randoms()

    def tearDown(self):
        self.temp.cleanup()

    def test_parse_library_tree_and_metadata(self):
        second = make_cbr(b"", title="第二局", red_first=False)
        library = cbl.parse_cbl(make_cbl([branching_game(), second], "棋库名称"))

        self.assertEqual(library.name, "棋库名称")
        self.assertEqual(library.declared_count, 1)
        self.assertEqual(len(library.games), 2)
        game = library.games[0]
        self.assertEqual(game.title, "测试棋谱")
        self.assertEqual(game.event, "测试赛事")
        self.assertEqual(game.red, "红方")
        self.assertEqual(game.black, "黑方")
        self.assertEqual(game.result, 4)
        self.assertTrue(game.red_first)
        self.assertEqual(game.board, standard_board())
        self.assertEqual(game.annotation, "棋谱注解")
        self.assertEqual(game.source_offset, cbl.cbl_data_offset(1))
        self.assertEqual(len(game.moves), 2)
        first, variation = game.moves
        self.assertEqual((first.source, first.target), (70, 67))
        self.assertEqual(first.annotation, "首着注解")
        self.assertEqual(len(first.children), 1)
        self.assertEqual((first.children[0].source, first.children[0].target), (7, 24))
        self.assertEqual((variation.source, variation.target), (56, 47))
        self.assertFalse(library.games[1].red_first)
        self.assertEqual(library.games[1].title, "第二局")
        self.assertEqual(library.games[1].source_offset,
                         cbl.cbl_data_offset(1) + cbl.CBL_RECORD_SIZE)

    def test_convert_cbl_weights_and_max_plies(self):
        path = self.root / "input.cbl"
        path.write_bytes(make_cbl([branching_game(), branching_game()]))

        stats = co.import_cbl(path, builder := co.BookBuilder(), self.randoms)

        self.assertEqual(stats.cbl_games, 2)
        self.assertEqual(stats.cbl_moves, 6)
        self.assertEqual(stats.cbl_skipped_branches, 0)
        start_key = co.jqxq_key(co.Board.from_fen(co.START), self.randoms)
        child = co.Board.from_fen(co.START).apply((70, 67))
        child_key = co.jqxq_key(child, self.randoms)
        self.assertEqual(builder.entries(), sorted([
            (start_key, co.encoded_move((70, 67)), 2, 0),
            (start_key, co.encoded_move((56, 47)), 2, 0),
            (child_key, co.encoded_move((7, 24)), 2, 0),
        ]))

        limited = co.import_cbl(path, limited_builder := co.BookBuilder(), self.randoms,
                                max_plies=1)
        self.assertEqual(limited.cbl_moves, 4)
        self.assertEqual(len(limited_builder.entries()), 2)

    def test_make_book_skips_illegal_branch_and_keeps_variation(self):
        moves = (
            move(70, 67, mark=2)
            + move(0, 1, mark=0)
            + move(7, 24)
            + move(56, 47)
        )
        path = self.root / "input.cbl"
        output = self.root / "book.bin"
        path.write_bytes(make_cbl([make_cbr(moves)]))

        _, stats, summary = co.make_book(path, output)

        self.assertEqual(stats.source_format, "CBL")
        self.assertEqual(stats.cbl_moves, 2)
        self.assertEqual(stats.cbl_skipped_branches, 1)
        self.assertEqual(stats.cbl_skipped_moves, 2)
        self.assertEqual(summary["entries"], 2)
        self.assertEqual(co.verify_book(output), summary)

    def test_query_fen_key_demo_and_check(self):
        path = self.root / "query.cbl"
        path.write_bytes(make_cbl([branching_game(), branching_game()], "查询棋库"))
        start_key = co.obk_key(co.Board.from_fen(co.START))

        output = run_obk(["--db", path, co.START])
        self.assertIn(f"vkey: {start_key}", output)
        self.assertIn("棋库: 查询棋库", output)
        self.assertIn("命中 2 条开局库着法", output)
        self.assertIn("次数", output)
        self.assertIn("首着注解", output)
        self.assertRegex(output, r"炮二平五\s+h2-e2\s+2")
        self.assertRegex(output, r"兵七进一\s+c3-c4\s+2")

        output = run_obk(["--db", path, "--key", start_key])
        self.assertRegex(output, r"<move=43687>\s+2")
        output = run_obk(["--db", path, "--demo"])
        self.assertIn(f"vkey: {start_key}", output)
        self.assertNotIn("15265892774299731920", output)

        output = run_obk(["--db", path, "--check"])
        self.assertIn("检查结果: 合法", output)
        self.assertIn("CBL 棋谱: 2, 合法着法: 6, 跳过分支: 0, 跳过非法着法: 0", output)

    def test_query_play_batch_interactive_and_out_of_book(self):
        path = self.root / "play.cbl"
        path.write_bytes(make_cbl([branching_game()]))
        for moves in (["炮二平五", "马8进7"], ["H2-E2", "H9-G7"]):
            with self.subTest(moves=moves):
                output = run_obk(["--db", path, "--play", *moves])
                self.assertIn("第 1 步 红: 炮二平五 h2-e2  [在谱] 次数1", output)
                self.assertIn("第 2 步 黑: 马8进7 h9-g7  [在谱] 次数1", output)
                self.assertIn("分叉(0)", output)

        output = run_obk(["--db", path, "--play", "e0-e1", "h9-g7"])
        self.assertIn("第 1 步 红: 帅五进一 e0-e1  [脱谱]", output)
        self.assertIn("第 2 步 黑: 马8进7 h9-g7  [已出谱]", output)
        output = run_obk(["--db", path, "--play"], input_text="炮二平五\nb\nq\n")
        self.assertIn("已回退到第 1 步 红走子", output)

    def test_query_check_rejects_corruption_and_reports_illegal_branches(self):
        corrupt = self.root / "corrupt.cbl"
        corrupt.write_bytes(b"not a CBL library")
        output = run_obk(["--db", corrupt, "--check"], expected_code=1)
        self.assertIn("检查结果: 不合法", output)

        moves = move(70, 67, mark=0) + move(0, 1, mark=0) + move(7, 24)
        path = self.root / "illegal.cbl"
        path.write_bytes(make_cbl([make_cbr(moves)]))
        output = run_obk(["--db", path, "--check"])
        self.assertIn("检查结果: 合法", output)
        self.assertIn("跳过分支: 1, 跳过非法着法: 2", output)

    def test_empty_library_and_malformed_inputs(self):
        header = struct.pack(
            "<16s44si512s", cbl.CBL_MAGIC, b"", 1, fixed_text("空库", 512))
        data = header.ljust(cbl.cbl_data_offset(1), b"\x00")
        self.assertEqual(cbl.parse_cbl(data).games, [])
        with self.assertRaisesRegex(cbl.CBLError, "signature"):
            cbl.parse_cbl(b"bad" + data[3:])
        with self.assertRaisesRegex(cbl.CBLError, "truncated header"):
            cbl.parse_cbr(b"short")
        with self.assertRaisesRegex(cbl.CBLError, "outside the board"):
            cbl.parse_cbr(make_cbr(move(90, 0)))
        board = bytearray(standard_board())
        board[0] = 0x7F
        with self.assertRaisesRegex(cbl.CBLError, "unknown piece"):
            cbl.parse_cbr(make_cbr(b"", board=bytes(board)))


if __name__ == "__main__":
    unittest.main()
