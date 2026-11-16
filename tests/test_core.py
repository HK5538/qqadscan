"""核心逻辑测试：解码、规则、评分、词库、插件、报告。

运行：``python -m unittest discover -s tests -v``
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qqadscan.config import Config  # noqa: E402
from qqadscan.core.decoder import decode_line  # noqa: E402
from qqadscan.core.lexicon import Lexicon  # noqa: E402
from qqadscan.core.numerals import cn_to_int  # noqa: E402
from qqadscan.core.report import write_reports  # noqa: E402
from qqadscan.core.rules import RuleEngine  # noqa: E402
from qqadscan.core.scanner import ScanOptions, Scanner  # noqa: E402
from qqadscan.core.scorer import Scorer  # noqa: E402
from qqadscan.paths import AppPaths  # noqa: E402
from qqadscan.plugins.loader import PluginManager  # noqa: E402

EXAMPLE = "㈡〔〔氿▲4⊥〖婈４□（叁5〓>⒍思蒐←索≌q羣："


class BaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = Config.load(ROOT / "config.json")
        cls.lexicon = Lexicon.load(ROOT / "lexicon")

    def decode(self, text: str, **kwargs):
        params = dict(
            min_digits=self.config.min_digits,
            max_digits=self.config.max_digits,
            max_gap=self.config.max_gap,
            boundaries=self.config.boundary_chars,
            noise_precedence=self.config.noise_precedence,
            place_value=self.config.chinese_place_value,
        )
        params.update(kwargs)
        return decode_line(text, self.lexicon, **params)

    def evaluate(self, text: str):
        scorer = Scorer(self.config, self.lexicon)
        rules = RuleEngine(self.config, self.lexicon)
        results = []
        for candidate in self.decode(text):
            analysis = scorer.analyze(candidate)
            evaluation = rules.evaluate(
                candidate, has_group_evidence=analysis.has_group_evidence
            )
            if evaluation.skipped:
                continue
            score = scorer.score(candidate, analysis, evaluation)
            results.append((candidate, analysis, evaluation, score))
        return results


class TestLexicon(BaseCase):
    def test_files_loaded(self) -> None:
        stats = self.lexicon.stats()
        self.assertGreaterEqual(stats["files"], 10)
        self.assertGreater(stats["digit_mappings"], 300)
        self.assertGreater(stats["group_keywords"], 30)

    def test_digits_are_correct(self) -> None:
        # 防止「零〇一二三四」错位的回归测试
        expected = {
            "零": 0,
            "〇": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "叁": 3,
            "玖": 9,
        }
        for token, digit in expected.items():
            self.assertEqual(self.lexicon.digits[token].digit, digit, token)

    def test_symbols(self) -> None:
        cases = {"①": 1, "⑨": 9, "㈡": 2, "㊈": 9, "４": 4, "Ⅰ": 1, "⓵": 1}
        for token, digit in cases.items():
            self.assertEqual(self.lexicon.digits[token].digit, digit, token)

    def test_remove_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "a.tsv").write_text(
                "token\tcategory\tvalue\tkind\tweight\tnote\n"
                "氿\tdigit\t9\thomophone\t0.9\t\n",
                encoding="utf-8",
            )
            (folder / "b_override.tsv").write_text(
                "token\tcategory\tvalue\tkind\tweight\tnote\n"
                "!氿\tdigit\t\t\t\t\n",
                encoding="utf-8",
            )
            lex = Lexicon.load(folder)
            self.assertNotIn("氿", lex.digits)

    def test_last_file_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "a.tsv").write_text(
                "token\tcategory\tvalue\tkind\tweight\tnote\n"
                "㈱\tdigit\t9\tsymbol\t0.5\t\n",
                encoding="utf-8",
            )
            (folder / "z.tsv").write_text(
                "token\tcategory\tvalue\tkind\tweight\tnote\n"
                "㈱\tdigit\t7\tsymbol\t0.9\t覆盖\n",
                encoding="utf-8",
            )
            lex = Lexicon.load(folder)
            self.assertEqual(lex.digits["㈱"].digit, 7)


class TestNumerals(unittest.TestCase):
    def test_place_value(self) -> None:
        cases = {
            "十五": 15,
            "二十五": 25,
            "一百二十三": 123,
            "两千": 2000,
            "一万二千三百": 12300,
            "一百零五": 105,
            "二〇二六": 2026,
        }
        for text, value in cases.items():
            self.assertEqual(cn_to_int(text), value, text)

    def test_invalid(self) -> None:
        self.assertIsNone(cn_to_int("abc"))
        self.assertIsNone(cn_to_int(""))


class TestDecoder(BaseCase):
    def test_user_example(self) -> None:
        candidates = self.decode(EXAMPLE)
        self.assertTrue(candidates, "示例应至少解出一个号码")
        best = max(candidates, key=lambda c: len(c.digits))
        self.assertEqual(best.digits, "29443564")
        self.assertEqual(best.kinds.get("symbol"), 3)
        self.assertGreaterEqual(best.noise_count, 8)

    def test_pinyin(self) -> None:
        candidates = self.decode("资源群：jiu si wu san er liu qi 懂的都懂")
        self.assertEqual([c.digits for c in candidates], ["9453267"])

    def test_fullwidth_and_circled(self) -> None:
        self.assertEqual([c.digits for c in self.decode("群号是 ９４３８２１７６５")], ["943821765"])
        self.assertEqual([c.digits for c in self.decode("加裙⑧⑦②③①⑨")], ["872319"])

    def test_pinyin_word_boundary(self) -> None:
        # sans-serif 里的 san 不应该被当成 3；独立的拼音要能命中
        self.assertIsNone(self.lexicon.digit_at("sans", 0))
        self.assertIsNotNone(self.lexicon.digit_at("jiu si wu", 0))
        self.assertEqual(self.lexicon.digit_at("jiu si wu", 0).digit, 9)

    def test_gap_limit(self) -> None:
        # 间隔 3 个噪音字符仍然可以连起来
        self.assertNotEqual(self.decode("12▲△▽345"), [])
        # 间隔 4 个则断开
        self.assertEqual(self.decode("12▲△▽◆34"), [])

    def test_low_confidence_homophone_not_glued(self) -> None:
        # 「老司机」的「司」不应粘到前面的号码上
        candidates = self.decode("群号是 943821765 老司机带你上车")
        self.assertEqual([c.digits for c in candidates], ["943821765"])

    def test_chinese_numeral_value(self) -> None:
        # 默认阈值下「一百二十三」换算后只有 3 位，不作为群号候选
        self.assertEqual(self.decode("一百二十三"), [])
        candidates = self.decode("一百二十三", min_digits=3)
        self.assertEqual(candidates[0].digits, "123")
        self.assertEqual(candidates[0].numeric_value, 123)


class TestRules(BaseCase):
    def test_quantifier_excluded(self) -> None:
        self.assertEqual(self.evaluate("一百二十三块的全套资料，打包下载。"), [])
        self.assertEqual(self.evaluate("售价￥2999，限时特价。"), [])

    def test_time_excluded(self) -> None:
        self.assertEqual(self.evaluate("会议时间 18:10:30，请准时参加。"), [])
        self.assertEqual(self.evaluate("下午三点开会"), [])

    def test_date_excluded(self) -> None:
        self.assertEqual(self.evaluate("2026-11-17 18:10:30 系统日志"), [])

    def test_pure_arabic_without_group_skipped(self) -> None:
        self.assertEqual(self.evaluate("随机生成的数字 938271645 用于测试"), [])

    def test_pure_arabic_with_group_kept(self) -> None:
        results = self.evaluate("我的QQ号是 123456789，有空加我聊。")
        self.assertTrue(results)
        self.assertGreaterEqual(results[0][3].score, 40)

    def test_phone_excluded(self) -> None:
        self.assertEqual(self.evaluate("电话 13800138000 打给我"), [])

    def test_obfuscated_ad_scores_high(self) -> None:
        results = self.evaluate(EXAMPLE)
        self.assertTrue(results)
        best = max(results, key=lambda item: item[3].score)
        self.assertGreaterEqual(best[3].score, 75)
        self.assertEqual(best[3].band, "A")

    def test_always_mode(self) -> None:
        config = Config.load(ROOT / "config.json")
        config.set("always", "rules", "pure_arabic")
        rules = RuleEngine(config, self.lexicon)
        candidate = self.decode("QQ群 123456789")[0]
        evaluation = rules.evaluate(candidate, has_group_evidence=True)
        self.assertTrue(evaluation.skipped)

    def test_rule_off_mode(self) -> None:
        config = Config.load(ROOT / "config.json")
        config.set("off", "rules", "time")
        rules = RuleEngine(config, self.lexicon)
        candidates = decode_line(
            "会议时间 18:10:30",
            self.lexicon,
            min_digits=5,
            max_gap=3,
            boundaries=config.boundary_chars,
        )
        self.assertTrue(candidates)
        evaluation = rules.evaluate(candidates[0], has_group_evidence=False)
        self.assertFalse([hit for hit in evaluation.hits if hit.code == "time"])


class TestScorer(BaseCase):
    def test_bands(self) -> None:
        scorer = Scorer(self.config, self.lexicon)
        self.assertEqual(scorer.band_for(90), "A")
        self.assertEqual(scorer.band_for(60), "B")
        self.assertEqual(scorer.band_for(40), "C")
        self.assertEqual(scorer.band_for(10), "D")

    def test_reasons_are_explainable(self) -> None:
        results = self.evaluate(EXAMPLE)
        best = max(results, key=lambda item: item[3].score)
        labels = [reason.label for reason in best[3].reasons]
        self.assertIn("号码长度", labels)
        self.assertIn("群关键词", labels)
        self.assertIn("伪装程度", labels)

    def test_score_bounded(self) -> None:
        for text in (EXAMPLE, "QQ群 123456789", "加裙⑧⑦②③①⑨"):
            for _, _, _, score in self.evaluate(text):
                self.assertGreaterEqual(score.score, 0)
                self.assertLessEqual(score.score, 100)


class TestPlugins(BaseCase):
    def _paths(self, root: Path) -> AppPaths:
        return AppPaths(
            root=root,
            lexicon=root / "lexicon",
            config=root / "config.json",
            reports=root / "reports",
            plugins=root / "plugins",
        ).ensure()

    def test_builtin_plugins_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = PluginManager(self.config, self.lexicon, self._paths(Path(tmp)))
            manager.load()
            names = manager.names
            self.assertIn("contact_signals", names)
            self.assertIn("group_context", names)
            self.assertFalse(manager.errors, manager.errors)

    def test_external_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "plugins" / "tester"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "plugin.json").write_text(
                json.dumps(
                    {
                        "name": "tester",
                        "version": "1.0",
                        "entry": "plugin.py",
                        "class": "TesterPlugin",
                        "enabled": True,
                    }
                ),
                encoding="utf-8",
            )
            (plugin_dir / "plugin.py").write_text(
                "from qqadscan.plugins.api import PluginBase, ScoreDelta\n"
                "class TesterPlugin(PluginBase):\n"
                "    name = 'tester'\n"
                "    def adjust_score(self, candidate, analysis, ctx):\n"
                "        return [ScoreDelta(5, '测试加分')]\n",
                encoding="utf-8",
            )
            manager = PluginManager(self.config, self.lexicon, self._paths(root))
            manager.load()
            self.assertIn("tester", manager.names)
            candidate = self.decode("加裙⑧⑦②③①⑨")[0]
            deltas = manager.adjust_score(candidate, manager.context and Scorer(self.config, self.lexicon).analyze(candidate))
            self.assertTrue(any(d.label == "测试加分" for d in deltas))

    def test_broken_plugin_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "plugins" / "boom"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "plugin.py").write_text(
                "raise RuntimeError('boom')\n", encoding="utf-8"
            )
            manager = PluginManager(self.config, self.lexicon, self._paths(root))
            manager.load()
            self.assertTrue(any("boom" in err for err in manager.errors))


class TestScannerAndReport(BaseCase):
    def test_scan_sample(self) -> None:
        manager = PluginManager(
            self.config,
            self.lexicon,
            AppPaths(
                root=ROOT,
                lexicon=ROOT / "lexicon",
                config=ROOT / "config.json",
                reports=ROOT / "reports",
                plugins=ROOT / "plugins",
            ),
        )
        manager.load()
        scanner = Scanner(self.config, self.lexicon, manager)
        result = scanner.scan(ScanOptions(paths=[ROOT / "samples" / "demo.txt"], min_score=0))
        self.assertGreater(result.lines_scanned, 20)
        self.assertTrue(result.entries)
        digits = {entry.digits for entry in result.entries}
        self.assertIn("29443564", digits)
        self.assertIn("872319", digits)
        # 正常聊天/价格/时间不应出现
        self.assertNotIn("123", digits)
        self.assertNotIn("181030", digits)

        with tempfile.TemporaryDirectory() as tmp:
            written = write_reports(result, Path(tmp), formats=["txt", "csv", "json"])
            self.assertEqual(len(written), 3)
            for path in written:
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 100)
            payload = json.loads((Path(tmp) / written[2].name).read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total_hits"], result.total_hits)

    def test_encoding_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gbk.txt"
            path.write_bytes("加裙⑧⑦②③①⑨ 免费资源".encode("gbk"))
            scanner = Scanner(self.config, self.lexicon, None)
            result = scanner.scan(ScanOptions(paths=[path]))
            self.assertEqual(result.files_scanned, 1)
            self.assertTrue(result.entries)


if __name__ == "__main__":
    unittest.main(verbosity=2)
