import sqlite3
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import convert_obk as co


class ConvertObkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.randoms = co.load_jqxq_randoms()
        self.start = co.Board.from_fen(co.START)

    def tearDown(self):
        self.temp.cleanup()

    def create_obk(self, rows):
        path = self.root / "input.obk"
        connection = sqlite3.connect(path)
        connection.execute("DROP TABLE IF EXISTS bhobk")
        connection.execute("CREATE TABLE bhobk(vkey,vmove,vwin,vdraw,vlost,vvalid)")
        connection.executemany("INSERT INTO bhobk VALUES(?,?,?,?,?,?)", rows)
        connection.commit()
        connection.close()
        return path

    def fixture(self):
        child = self.start.apply(co.decode_obk_move(0xAAA7))
        child_key = co.obk_key(child)
        stored_child = struct.unpack("<d", struct.pack("<Q", child_key))[0]
        path = self.create_obk([
            (co.obk_key(self.start), 0xAAA7, 2, 1, 0, 1),
            (co.obk_key(self.start), 50341, 9, 9, 9, 0),
            (stored_child, 0x3A59, 4, 0, 1, 1),
            (0x5555, 0xAAA7, 8, 0, 0, 1),
            (None, 0xAAA7, 1, 0, 0, 1),
            (co.obk_key(self.start), 0x9585, 0, 0, 0, 1),
        ])
        return path, child, child_key

    def test_key_and_move_anchors(self):
        self.assertEqual(co.obk_key(self.start), 7101337512282506414)
        self.assertEqual(co.jqxq_key(self.start, self.randoms), 0x52DFA0347C3B4C0F)
        black = co.Board(self.start.cells, 1)
        self.assertEqual(co.jqxq_key(black, self.randoms),
                         0x52DFA0347C3B4C0F ^ self.randoms[3840])
        self.assertEqual(co.decode_obk_move(0xAAA7), (70, 67))
        self.assertEqual(co.decode_obk_move(0x3A59), (7, 24))
        self.assertEqual(co.encoded_move((70, 67)), 0xAAA7)
        self.assertEqual(co.encoded_move((7, 24)), 0x3A59)
        with self.assertRaisesRegex(co.BookError, "outside the board"):
            co.decode_obk_move(0)

    def test_integer_and_real_key_recovery(self):
        key = 0xFEDCBA9876543210
        real = struct.unpack("<d", struct.pack("<Q", key))[0]
        self.assertEqual(co.uint64_sql_value(real, "test"), key)
        self.assertEqual(co.uint64_sql_value(key - (1 << 64), "test"), key)
        with self.assertRaisesRegex(co.BookError, "INTEGER or FLOAT"):
            co.uint64_sql_value("bad", "test")

    def test_builder_merge_saturation_sorting_and_atomic_output(self):
        builder = co.BookBuilder()
        builder.add(2, 0xAAA7, 3)
        builder.add(1, 0xAAA7, 65535)
        builder.add(1, 0xAAA7, 100)
        self.assertEqual(builder.entries(), [(1, 0xAAA7, 65535, 0), (2, 0xAAA7, 3, 0)])
        self.assertEqual(builder.saturations, 1)
        data = builder.serialize()
        self.assertEqual(co.verify_book(data), {"entries": 2, "positions": 2, "bytes": 32})
        first, second = self.root / "one.bin", self.root / "two.bin"
        co.atomic_write(first, data)
        co.atomic_write(second, data)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_verify_rejects_corruption(self):
        valid = co.ENTRY.pack(1, 0xAAA7, 1, 0)
        cases = [
            (b"bad", "multiple of 16"),
            (co.ENTRY.pack(2, 1, 1, 0) + co.ENTRY.pack(1, 1, 1, 0), "strictly"),
            (valid + valid, "strictly"),
            (co.ENTRY.pack(1, 0xAAA7, 0, 0), "zero count"),
            (co.ENTRY.pack(1, 0xAAA7, 1, 1), "nonzero learn"),
        ]
        for data, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(co.BookError, message):
                    co.verify_book(data)

    def test_import_valid_zero_disabled_real_unreachable_and_null(self):
        path, child, _ = self.fixture()
        builder = co.BookBuilder()
        stats = co.import_obk(path, builder, self.randoms)
        self.assertEqual(stats.sqlite_records, 6)
        self.assertEqual(stats.observations, 2)
        self.assertEqual(stats.disabled_records, 1)
        self.assertEqual(stats.zero_weight_records, 1)
        self.assertEqual(stats.unmatched_records, 2)
        self.assertEqual(builder.entries(), sorted([
            (co.jqxq_key(child, self.randoms), 0x3A59, 5, 0),
            (co.jqxq_key(self.start, self.randoms), 0xAAA7, 3, 0),
        ]))
        self.assertEqual(co.verify_book(builder.serialize())["entries"], 2)

    def test_import_max_plies_and_illegal_move(self):
        path, _, _ = self.fixture()
        builder = co.BookBuilder()
        stats = co.import_obk(path, builder, self.randoms, max_plies=0)
        self.assertEqual(builder.entries(), [])
        self.assertEqual(stats.unmatched_records, 6)
        illegal = self.create_obk([(co.obk_key(self.start), 0x3334, 1, 0, 0, 1)])
        with self.assertRaisesRegex(co.BookError, "rowid 1.*not legal"):
            co.import_obk(illegal, co.BookBuilder(), self.randoms)

    def test_negative_weight_is_rejected(self):
        path = self.create_obk([(co.obk_key(self.start), 0xAAA7, -1, 0, 0, 1)])
        with self.assertRaisesRegex(co.BookError, "nonnegative integer"):
            co.import_obk(path, co.BookBuilder(), self.randoms)


if __name__ == "__main__":
    unittest.main()
