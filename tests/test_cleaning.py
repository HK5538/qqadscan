"""删除与输出功能的测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qqadscan.config import Config  # noqa: E402
from qqadscan.core.cleaning import (  # noqa: E402
    AUDIT_NAME,
    CleanPlan,
    build_plan,
    clean_file,
    run_plan,
)
from qqadscan.core.lexicon import Lexicon  # noqa: E402
from qqadscan.core.scanner import ScanOptions, Scanner  # noqa: E402


class CleaningCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make(self, name: str, content: str, encoding: str = "utf-8") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode(encoding))
        return path


class TestCleanFile(CleaningCase):
    def test_drops_selected_lines(self) -> None:
        source = self.make("a.txt", "第一行\n第二行\n第三行\n第四行\n第五行\n")
        target = self.root / "out" / "a_已清理.txt"
        outcome = clean_file(source, target, {2, 4})
        self.assertTrue(outcome.ok, outcome.error)
        self.assertEqual(outcome.removed, 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "第一行\n第三行\n第五行\n")
        # 原文件必须一个字节都没变
        self.assertEqual(source.read_text(encoding="utf-8"), "第一行\n第二行\n第三行\n第四行\n第五行\n")

    def test_preserves_crlf_and_bom(self) -> None:
        source = self.make("b.txt", "广告一\r\n正常二\r\n广告三\r\n", encoding="utf-8-sig")
        target = self.root / "b_out.txt"
        outcome = clean_file(source, target, {1, 3})
        self.assertTrue(outcome.ok, outcome.error)
        raw = target.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "BOM 应保留")
        self.assertIn(b"\r\n", raw, "CRLF 应保留")
        self.assertIn("正常二".encode("utf-8"), raw)

    def test_preserves_gbk(self) -> None:
        source = self.make("gbk.txt", "第一行\n加裙⑧⑦②③①⑨\n第三行\n", encoding="gb18030")
        target = self.root / "gbk_out.txt"
        outcome = clean_file(source, target, {2})
        self.assertTrue(outcome.ok, outcome.error)
        self.assertEqual(target.read_bytes().decode("gb18030"), "第一行\n第三行\n")

    def test_overwrite_creates_backup(self) -> None:
        source = self.make("c.txt", "keep\ndrop\nkeep2\n")
        outcome = clean_file(source, source, {2}, overwrite=True, backup=True)
        self.assertTrue(outcome.ok, outcome.error)
        self.assertIsNotNone(outcome.backup)
        self.assertTrue(outcome.backup.is_file())
        self.assertEqual(outcome.backup.read_text(encoding="utf-8"), "keep\ndrop\nkeep2\n")
        self.assertEqual(source.read_text(encoding="utf-8"), "keep\nkeep2\n")

    def test_refuses_overwrite_without_flag(self) -> None:
        source = self.make("d.txt", "a\nb\n")
        outcome = clean_file(source, source, {1}, overwrite=False)
        self.assertFalse(outcome.ok)
        self.assertEqual(source.read_text(encoding="utf-8"), "a\nb\n")

    def test_missing_file(self) -> None:
        outcome = clean_file(self.root / "nope.txt", self.root / "x.txt", {1})
        self.assertFalse(outcome.ok)


class TestRunPlan(CleaningCase):
    def test_keeps_relative_structure_and_audit(self) -> None:
        first = self.make("sub1/a.txt", "1\n2\n3\n")
        second = self.make("sub1/sub2/b.txt", "x\ny\nz\n")
        plan = CleanPlan()
        plan.add(first, 2)
        plan.add(second, 3)

        out = self.root / "output"
        outcomes = run_plan(plan, out, suffix="_已清理")
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(all(item.ok for item in outcomes), [item.error for item in outcomes])
        # 输出以「这些文件的共同父目录」为基准，保持相对结构
        self.assertEqual((out / "a_已清理.txt").read_text(encoding="utf-8"), "1\n3\n")
        self.assertTrue((out / "sub2" / "b_已清理.txt").is_file())
        self.assertTrue((out / AUDIT_NAME).is_file())

    def test_duplicate_names_do_not_overwrite(self) -> None:
        first = self.make("x/a.txt", "1\n2\n")
        second = self.make("y/a.txt", "3\n4\n")
        plan = CleanPlan()
        plan.add(first, 1)
        plan.add(second, 1)
        outcomes = run_plan(plan, self.root / "output")
        targets = {str(item.target) for item in outcomes}
        self.assertEqual(len(targets), 2, targets)

    def test_empty_plan(self) -> None:
        self.assertEqual(run_plan(CleanPlan(), self.root / "output"), [])


class TestPlanFromScan(CleaningCase):
    def test_scanner_attaches_source_path(self) -> None:
        self.make("demo.txt", "加裙⑧⑦②③①⑨ 免费资源\n今天下午三点开会\n")
        config = Config.load(ROOT / "config.json")
        lexicon = Lexicon.load(ROOT / "lexicon")
        scanner = Scanner(config, lexicon, None)
        result = scanner.scan(ScanOptions(paths=[self.root / "demo.txt"]))

        self.assertTrue(result.entries)
        entry = result.entries[0]
        self.assertIsNotNone(entry.source_path)
        self.assertTrue(Path(entry.source_path).is_file())
        self.assertEqual(entry.line_no, 1)

        plan = build_plan(result.entries)
        self.assertEqual(plan.total_lines, 1)
        self.assertIn(Path(entry.source_path), plan.files)

    def test_relative_roots_in_result(self) -> None:
        self.make("demo.txt", "加裙⑧⑦②③①⑨ 免费资源\n")
        config = Config.load(ROOT / "config.json")
        lexicon = Lexicon.load(ROOT / "lexicon")
        result = Scanner(config, lexicon, None).scan(ScanOptions(paths=[self.root]))
        self.assertTrue(result.roots)
        self.assertFalse(Path(result.roots[0]).is_absolute(), result.roots[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
