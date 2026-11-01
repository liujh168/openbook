import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "bhobk.exe"
START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
START_KEY = 7101337512282506414
DEMO_KEY = 15265892774299731920

INITIAL_ROWS = [
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
DEMO_ROWS = {
    50341: (1, 0, 1, 0, 0),
    42151: (-2, 0, 0, 1, 0),
}

RAW_ROW_RE = re.compile(
    r"<move=(\d+)>\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"
)
FEN_ROW_RE = re.compile(
    r"^\s*(\S+)\s+([a-i]\d+-[a-i]\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
    re.MULTILINE,
)


def run_tool(args, expected_code=0, python=False):
    command = [sys.executable, str(ROOT / "obk.py")] if python else [str(EXE)]
    result = subprocess.run(
        command + list(args),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    if result.returncode != expected_code:
        raise AssertionError(
            f"命令 {command + list(args)} 退出码为 {result.returncode}，"
            f"预期 {expected_code}\n{result.stdout}"
        )
    return result.stdout


def raw_rows(output):
    return {
        int(match.group(1)): tuple(int(value) for value in match.groups()[1:])
        for match in RAW_ROW_RE.finditer(output)
    }


def raw_scores(output):
    return [int(match.group(2)) for match in RAW_ROW_RE.finditer(output)]


def fen_rows(output):
    return {
        match.group(2): (
            match.group(1),
            *(int(value) for value in match.groups()[2:]),
        )
        for match in FEN_ROW_RE.finditer(output)
    }


def fen_scores(output):
    return [int(match.group(3)) for match in FEN_ROW_RE.finditer(output)]


class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["cmd.exe", "/c", "build.bat"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"构建失败：\n{result.stdout}")

    def test_initial_key_query_golden_rows(self):
        output = run_tool(["--key", str(START_KEY)])
        expected = {row[0]: row[3:] for row in INITIAL_ROWS}
        self.assertIn(f"vkey: {START_KEY}", output)
        self.assertIn("命中 15 条开局库着法", output)
        self.assertEqual(raw_rows(output), expected)
        self.assertEqual(raw_scores(output), sorted(raw_scores(output), reverse=True))

    def test_initial_fen_translation_golden_rows(self):
        output = run_tool([START_FEN])
        expected = {row[2]: (row[1], *row[3:]) for row in INITIAL_ROWS}
        self.assertIn(f"vkey: {START_KEY}", output)
        self.assertEqual(fen_rows(output), expected)
        self.assertEqual(fen_scores(output), sorted(fen_scores(output), reverse=True))

    def test_c_python_initial_results_match(self):
        c_output = run_tool([START_FEN])
        python_output = run_tool([START_FEN], python=True)
        self.assertEqual(fen_rows(c_output), fen_rows(python_output))
        self.assertIn(f"vkey: {START_KEY}", python_output)

    def test_high_bit_demo_key(self):
        for python in (False, True):
            with self.subTest(python=python):
                output = run_tool(["--demo"], python=python)
                self.assertIn(f"vkey: {DEMO_KEY}", output)
                self.assertIn("命中 2 条开局库着法", output)
                self.assertEqual(raw_rows(output), DEMO_ROWS)

    def test_play_known_iccs_line(self):
        output = run_tool(["--play", "h2-e2", "h7-e7"])
        self.assertIn("第 1 步 红: 炮二平五 h2-e2  [在谱] 评分949 胜292 和957 负296", output)
        self.assertIn("第 2 步 黑: 炮8平5 h7-e7  [在谱] 评分-1 胜0 和3 负2 (被禁)", output)
        self.assertRegex(output, r"当前轮到红,\s+分叉\(1\): 马二进三\(7\)")

    def test_play_known_chinese_line(self):
        output = run_tool(["--play", "炮二平五", "马8进7"])
        self.assertIn("第 1 步 红: 炮二平五 h2-e2  [在谱] 评分949", output)
        self.assertRegex(output, r"第 2 步 黑: 马8进7 h9-g7\s+\[在谱\] 评分874")

    def test_help_and_no_arguments(self):
        for option in ("-h", "--help"):
            with self.subTest(option=option):
                output = run_tool([option])
                self.assertIn("用法:", output)
                self.assertIn("--db <文件>", output)
                self.assertIn("--check", output)
        output = run_tool([])
        self.assertIn("使用 -h 或 --help 查看命令行帮助", output)
        self.assertIn(f"vkey: {START_KEY}", output)
        self.assertIn("命中 15 条开局库着法", output)

    def test_check_valid_default_and_explicit_db(self):
        cases = [
            ["--check"],
            ["--db", "test.obk", "--check"],
            ["--check", "--db", "test.obk"],
        ]
        for args in cases:
            with self.subTest(args=args):
                output = run_tool(args)
                self.assertIn("检查结果: 合法", output)
                self.assertIn("SQLite 快速检查及 bhobk 表必需字段检查均通过", output)

    def test_check_rejects_non_sqlite_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.obk"
            path.write_text("this is not an SQLite opening book\n", encoding="utf-8")
            output = run_tool(["--db", str(path), "--check"], expected_code=1)
            self.assertIn("检查结果: 不合法", output)

    def test_check_rejects_missing_book_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unrelated.obk"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE unrelated(value INTEGER)")
            connection.close()
            output = run_tool(["--db", str(path), "--check"], expected_code=1)
            self.assertIn("bhobk 表或必需字段缺失", output)

    def test_check_missing_file_does_not_create_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.obk"
            output = run_tool(["--db", str(path), "--check"], expected_code=1)
            self.assertIn("无法打开", output)
            self.assertFalse(path.exists())

    def test_db_and_check_argument_errors(self):
        output = run_tool(["--db"], expected_code=1)
        self.assertIn("--db 需要指定 .obk 文件名", output)
        output = run_tool(["--check", "--demo"], expected_code=1)
        self.assertIn("--check 不能与其他查询参数同时使用", output)

    def test_explicit_db_query_matches_default(self):
        default_output = run_tool(["--key", str(START_KEY)])
        explicit_output = run_tool(["--db", "test.obk", "--key", str(START_KEY)])
        self.assertEqual(raw_rows(explicit_output), raw_rows(default_output))


if __name__ == "__main__":
    unittest.main()
