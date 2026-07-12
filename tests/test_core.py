from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from diary_agent.core import DiaryStore, TZ


class DiaryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.store = DiaryStore(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def confirm_entry(self, text: str, date: str, theme: str = "生活") -> str:
        draft = self.store.create_draft(text, entry_date=date)
        self.store.save_preview(
            draft["entry_id"],
            text,
            [{"text": text, "theme": theme}],
        )
        self.store.confirm(draft["entry_id"])
        return draft["entry_id"]

    def test_draft_preview_confirm_and_idempotency(self):
        draft = self.store.create_draft("嗯，今天我继续整理日记系统。另外也去跑步了。")
        self.assertEqual(
            draft["routing_decision"]["stages"],
            {"clean": True, "classify": True, "continuity": True},
        )
        self.assertTrue(draft["routing_decision"]["delegate"]["cleaner"])
        original = next((self.root / "journals" / "originals").rglob("*.md"))
        self.assertIn("嗯，今天", original.read_text(encoding="utf-8"))

        self.store.save_preview(
            draft["entry_id"],
            "今天我继续整理日记系统。另外也去跑步了。",
            [
                {"text": "今天我继续整理日记系统。", "theme": "日记系统"},
                {"text": "另外也去跑步了。", "theme": "运动"},
            ],
            followups=[{"question": "日记系统下一步准备完善什么？"}],
        )
        result = self.store.confirm(draft["entry_id"])
        self.assertEqual(result["status"], "confirmed")
        self.assertIn("### 运动", Path(result["clean_path"]).read_text(encoding="utf-8"))
        self.assertTrue(self.store.confirm(draft["entry_id"])["idempotent"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM segments").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT count(*) FROM followups").fetchone()[0], 1)

    def test_dynamic_retrieval_uses_budget_not_fixed_count(self):
        for index in range(15):
            self.confirm_entry(
                f"跑步训练第{index}次，继续改善耐力和呼吸。",
                f"2026-06-{index + 1:02d}",
                "跑步",
            )
        small = self.store.search("跑步耐力", token_budget=100)
        large = self.store.search("跑步耐力", token_budget=4000)
        self.assertGreaterEqual(len(large), len(small))
        self.assertLessEqual(sum(len(item["text"]) for item in small), 600)
        self.assertTrue(all("score" in item for item in large))

    def test_weekly_context_skips_empty_and_uses_previous_week(self):
        self.store.initialize()
        now = datetime(2026, 7, 13, 1, 0, tzinfo=TZ)
        self.assertFalse(self.store.weekly_context(now)["has_content"])
        self.confirm_entry("上周记录", "2026-07-12")
        context = self.store.weekly_context(now)
        self.assertEqual(context["period_start"], "2026-07-06")
        self.assertEqual(context["period_end"], "2026-07-12")
        self.assertEqual(len(context["entries"]), 1)

    def test_feedback_and_backup(self):
        feedback = self.store.add_feedback("主题预览太长", "inconvenience")
        review = self.store.feedback_review_context(datetime.now(TZ))
        self.assertTrue(review["has_feedback"])
        self.assertEqual(review["feedback"][0]["id"], feedback["feedback_id"])
        backup = self.store.backup()
        self.assertTrue(Path(backup["database"]).exists())
        self.assertEqual(len(backup["sha256"]), 64)

    def test_no_openai_api_dependency(self):
        self.store.initialize()
        package = Path(__file__).parents[1] / "diary_agent"
        text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
        self.assertNotIn("OPENAI_API_KEY", text)
        self.assertNotIn("import openai", text)

    def test_skill_proposal_commits_database_and_journals(self):
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        self.confirm_entry("需要保存到 Git", "2026-07-12", "系统")
        feedback = self.store.add_feedback("希望自动提交")
        result = self.store.propose_skill_revision(
            {"feedback_ids": [feedback["feedback_id"]], "summary": "自动提交"}
        )
        self.assertTrue(result["snapshot_commit"])
        tracked = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("data/diary.sqlite3", tracked)
        self.assertIn("journals/originals/2026/07/", tracked)
        self.assertIn("journals/cleaned/2026/07/", tracked)


if __name__ == "__main__":
    unittest.main()
