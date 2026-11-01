import re
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "bhobk.exe"
START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
OBK_START_KEY = 7101337512282506414
OBK_DEMO_KEY = 15265892774299731920
JQXQ_START_KEY = 0x52DFA0347C3B4C0F

OBK_INITIAL_ROWS = [
    (43687, "炮二平五", "h2-e2", 949, 292, 957, 296, 1),
    (51623, "相三进五", "g0-e2", 576, 150, 462, 93, 1),
    (38277, "兵七进一", "c3-c4", 412, 146, 442, 161, 1),
    (50341, "马八进七", "b0-c2", 60, 20, 88, 34, 0),
    (43686, "炮二平六", "h2-d2", 19, 13, 77, 42, 0),
    (43691, "炮二平一", "h2-i2", 7, 3, 1, 0, 0),
    (43689, "炮二平三", "h2-g2", 4, 2, 2, 1, 0),
    (43706, "炮二退一", "h2-h1", 3, 1, 1, 0, 0),
    (42153, "炮八平三", "b2-g2", 3, 1, 3, 1, 0),
    (51383, "仕四进五", "f0-e1", 2, 1, 4, 2, 0),
    (50339, "马八进九", "b0-a2", -2, 0, 4, 3, 0),
    (43658, "炮二进二", "h2-h4", -2, 0, 0, 1, 0),
    (42150, "炮八平六", "b2-d2", -4, 0, 4, 4, 0),
    (43674, "炮二进一", "h2-h3", -4, 0, 0, 2, 0),
    (37763, "兵九进一", "a3-a4", -6, 0, 0, 3, 0),
]
OBK_DEMO_ROWS = {
    50341: (1, 0, 1, 0, 0),
    42151: (-2, 0, 0, 1, 0),
}
BOOK_INITIAL_ROWS = {
    43687: ("炮二平五", "h2-e2", 1545),
    38277: ("兵七进一", "c3-c4", 749),
    51623: ("相三进五", "g0-e2", 705),
}

OBK_RAW_RE = re.compile(r"<move=(\d+)>\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)")
OBK_FEN_RE = re.compile(
    r"^\s*(\S+)\s+([a-i]\d+-[a-i]\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
    re.MULTILINE,
)
BOOK_RAW_RE = re.compile(r"<move=(\d+)>\s+(\d+)")
BOOK_FEN_RE = re.compile(
    r"^\s*(\S+)\s+([a-i]\d+-[a-i]\d+)\s+(\d+)", re.MULTILINE)


def run_tool(args, expected_code=0, python=False):
    command = [sys.executable, str(ROOT / "obk.py")] if python else [str(EXE)]
    result = subprocess.run(
        command + list(args), cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", timeout=30)
    if result.returncode != expected_code:
        raise AssertionError(
            f"命令 {command + list(args)} 退出码为 {result.returncode}，"
            f"预期 {expected_code}\n{result.stdout}")
    return result.stdout


def obk_raw_rows(output):
    return {int(match.group(1)): tuple(int(value) for value in match.groups()[1:])
            for match in OBK_RAW_RE.finditer(output)}


def obk_fen_rows(output):
    return {match.group(2): (match.group(1), *(int(value) for value in match.groups()[2:]))
            for match in OBK_FEN_RE.finditer(output)}


def book_raw_rows(output):
    return {int(match.group(1)): int(match.group(2))
            for match in BOOK_RAW_RE.finditer(output)}


def book_fen_rows(output):
    return {iccs: int(weight) for _, iccs, weight in BOOK_FEN_RE.findall(output)}


def book_fen_translations(output):
    return {iccs: name for name, iccs, _ in BOOK_FEN_RE.findall(output)}


class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        commands = [
            [sys.executable, str(ROOT / "convert_obk.py")],
            ["cmd.exe", "/c", "build.bat"],
        ]
        for command in commands:
            result = subprocess.run(
                command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", timeout=120)
            if result.returncode != 0:
                raise RuntimeError(f"准备测试失败：{command}\n{result.stdout}")

    def test_python_obk_initial_golden_rows(self):
        output = run_tool([START_FEN], python=True)
        expected = {row[2]: (row[1], *row[3:]) for row in OBK_INITIAL_ROWS}
        self.assertIn(f"vkey: {OBK_START_KEY}", output)
        self.assertEqual(obk_fen_rows(output), expected)

    def test_python_obk_high_bit_demo(self):
        output = run_tool(["--demo"], python=True)
        self.assertIn(f"vkey: {OBK_DEMO_KEY}", output)
        self.assertEqual(obk_raw_rows(output), OBK_DEMO_ROWS)

    def test_initial_binary_key_and_weights(self):
        expected = {move: values[2] for move, values in BOOK_INITIAL_ROWS.items()}
        for key in (str(JQXQ_START_KEY), "0x52DFA0347C3B4C0F"):
            with self.subTest(key=key):
                output = run_tool(["--key", key])
                self.assertIn(f"vkey: {JQXQ_START_KEY}", output)
                self.assertIn("命中 3 条开局库着法", output)
                self.assertEqual(book_raw_rows(output), expected)
                weights = [int(match.group(2)) for match in BOOK_RAW_RE.finditer(output)]
                self.assertEqual(weights, sorted(weights, reverse=True))

    def test_initial_fen_translation_and_demo(self):
        output = run_tool([START_FEN])
        self.assertIn(f"vkey: {JQXQ_START_KEY}", output)
        self.assertEqual(book_fen_rows(output),
                         {values[1]: values[2] for values in BOOK_INITIAL_ROWS.values()})
        self.assertEqual(book_fen_translations(output),
                         {values[1]: values[0] for values in BOOK_INITIAL_ROWS.values()})
        demo = run_tool(["--demo"])
        self.assertEqual(book_raw_rows(demo), book_raw_rows(run_tool(["--key", str(JQXQ_START_KEY)])))

    def test_explicit_book_query_matches_default(self):
        default_output = run_tool(["--key", str(JQXQ_START_KEY)])
        explicit_output = run_tool(["--book", "book.bin", "--key", str(JQXQ_START_KEY)])
        self.assertEqual(book_raw_rows(explicit_output), book_raw_rows(default_output))

    def test_play_known_iccs_line(self):
        output = run_tool(["--play", "h2-e2", "h9-g7"])
        self.assertIn("第 1 步 红: 炮二平五 h2-e2  [在谱] 权重1545", output)
        self.assertIn("第 2 步 黑: 马8进7 h9-g7  [在谱] 权重1370", output)
        self.assertRegex(output, r"当前轮到红,\s+分叉\(5\): 马二进三\(905\)")

    def test_play_known_chinese_line(self):
        output = run_tool(["--play", "炮二平五", "马8进7"])
        self.assertIn("第 1 步 红: 炮二平五 h2-e2  [在谱] 权重1545", output)
        self.assertIn("第 2 步 黑: 马8进7 h9-g7  [在谱] 权重1370", output)

    def test_help_and_no_arguments(self):
        for option in ("-h", "--help"):
            with self.subTest(option=option):
                output = run_tool([option])
                self.assertIn("用法:", output)
                self.assertIn("--book <文件>", output)
                self.assertIn("--check", output)
        output = run_tool([])
        self.assertIn("使用 -h 或 --help 查看命令行帮助", output)
        self.assertIn(f"vkey: {JQXQ_START_KEY}", output)
        self.assertIn("命中 3 条开局库着法", output)

    def test_check_valid_default_and_explicit_book(self):
        for args in (["--check"], ["--book", "book.bin", "--check"]):
            with self.subTest(args=args):
                output = run_tool(args)
                self.assertIn("检查结果: 合法", output)
                self.assertIn("记录: 377, 局面: 285", output)

    def test_check_rejects_corrupt_books(self):
        valid = struct.pack("<QHHI", JQXQ_START_KEY, 0xAAA7, 1, 0)
        cases = {
            "truncated": (b"bad", "不是 16 的倍数"),
            "unsorted": (struct.pack("<QHHI", 2, 0xAAA7, 1, 0)
                         + struct.pack("<QHHI", 1, 0xAAA7, 1, 0), "严格排序"),
            "duplicate": (valid + valid, "严格排序"),
            "zero": (struct.pack("<QHHI", JQXQ_START_KEY, 0xAAA7, 0, 0), "权重为零"),
            "learn": (struct.pack("<QHHI", JQXQ_START_KEY, 0xAAA7, 1, 1), "learn 非零"),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, (data, message) in cases.items():
                with self.subTest(name=name):
                    path = Path(directory) / (name + ".bin")
                    path.write_bytes(data)
                    output = run_tool(["--book", str(path), "--check"], expected_code=1)
                    self.assertIn("检查结果: 不合法", output)
                    self.assertIn(message, output)

    def test_check_missing_file_does_not_create_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.bin"
            output = run_tool(["--book", str(path), "--check"], expected_code=1)
            self.assertIn("无法打开", output)
            self.assertFalse(path.exists())

    def test_argument_errors(self):
        output = run_tool(["--book"], expected_code=1)
        self.assertIn("--book 需要指定二进制开局库文件名", output)
        output = run_tool(["--check", "--demo"], expected_code=1)
        self.assertIn("--check 不能与其他查询参数同时使用", output)
        output = run_tool(["--key", "invalid"], expected_code=1)
        self.assertIn("无效的 vkey: invalid", output)


if __name__ == "__main__":
    unittest.main()
