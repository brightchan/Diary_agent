from __future__ import annotations

import subprocess
import sys
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

    def test_theme_governance_requires_confirmation_and_preserves_markdown(self):
        first = self.confirm_entry("今天散步并看了晚霞。", "2026-01-05", "远足")
        second = self.confirm_entry("整理户外装备。", "2026-01-06", "户外")
        with self.store.connect() as db:
            source = db.execute("SELECT * FROM themes WHERE name='远足'").fetchone()
            target = db.execute("SELECT * FROM themes WHERE name='户外'").fetchone()
            source_segment = db.execute("SELECT * FROM segments WHERE entry_id=?", (first,)).fetchone()
            target_segment = db.execute("SELECT * FROM segments WHERE entry_id=?", (second,)).fetchone()
        original_path = next((self.root / "journals" / "originals").rglob(f"*{first}.md"))
        clean_path = next((self.root / "journals" / "cleaned").rglob(f"*{first}.md"))
        original_bytes = original_path.read_bytes()
        clean_bytes = clean_path.read_bytes()

        rejected = self.store.save_theme_review([
            {"action": "rename", "source_theme_id": source["id"], "payload": {"name": "未批准的新名称"}}
        ])
        rejection = self.store.apply_theme_changes([{"proposal_id": rejected["proposals"][0]["proposal_id"], "decision": "rejected"}])
        self.assertFalse(rejection["results"][0]["idempotent"])
        repeated = self.store.apply_theme_changes([{"proposal_id": rejected["proposals"][0]["proposal_id"], "decision": "rejected"}])
        self.assertTrue(repeated["results"][0]["idempotent"])
        with self.store.connect() as db:
            unchanged = db.execute("SELECT name FROM themes WHERE id=?", (source["id"],)).fetchone()[0]
            audit = db.execute("SELECT status,decided_at,applied_at FROM theme_change_proposals WHERE id=?", (rejected["proposals"][0]["proposal_id"],)).fetchone()
        self.assertEqual(unchanged, "远足")
        self.assertEqual(audit[0], "rejected")
        self.assertTrue(audit[1])
        self.assertIsNone(audit[2])

        preview = self.store.save_theme_review([
            {"action": "deactivate", "source_theme_id": source["id"], "evidence": [{"entry_id": first}]}
        ])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM themes WHERE id=?", (source["id"],)).fetchone()[0], "active")
        self.store.apply_theme_changes([{"proposal_id": preview["proposals"][0]["proposal_id"], "decision": "approved"}])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM themes WHERE id=?", (source["id"],)).fetchone()[0], "inactive")
            self.assertEqual(db.execute("SELECT themes FROM entries_fts WHERE entry_id=?", (first,)).fetchone()[0], "")
            audit = db.execute("SELECT status,decided_at,applied_at FROM theme_change_proposals WHERE id=?", (preview["proposals"][0]["proposal_id"],)).fetchone()
        self.assertEqual(audit[0], "applied")
        self.assertTrue(audit[1])
        self.assertTrue(audit[2])
        blocked = self.store.create_draft("新的远足记录", entry_date="2026-01-07")
        self.store.save_preview(blocked["entry_id"], "新的远足记录", [{"text": "新的远足记录", "theme": "远足"}])
        with self.assertRaises(ValueError):
            self.store.confirm(blocked["entry_id"])
        self.assertTrue(any(item["entry_id"] == first for item in self.store.search("散步晚霞", 500)))
        self.assertEqual(original_path.read_bytes(), original_bytes)
        self.assertEqual(clean_path.read_bytes(), clean_bytes)

        activate = self.store.save_theme_review([{"action": "activate", "source_theme_id": source["id"]}])
        self.store.apply_theme_changes([{"proposal_id": activate["proposals"][0]["proposal_id"], "decision": "approved"}])
        merge = self.store.save_theme_review([{"action": "merge", "source_theme_id": source["id"], "target_theme_id": target["id"]}])
        self.store.apply_theme_changes([{"proposal_id": merge["proposals"][0]["proposal_id"], "decision": "approved"}])
        with self.store.connect() as db:
            merged = db.execute("SELECT status,merged_into FROM themes WHERE id=?", (source["id"],)).fetchone()
            self.assertEqual(tuple(merged), ("merged", target["id"]))
            self.assertEqual(db.execute("SELECT theme_id FROM segments WHERE id=?", (source_segment["id"],)).fetchone()[0], source["id"])
            self.assertIn("户外", db.execute("SELECT themes FROM entries_fts WHERE entry_id=?", (first,)).fetchone()[0])
        canonical_entry = self.confirm_entry("再次去山里散步。", "2026-01-08", "远足")
        with self.store.connect() as db:
            canonical_segment = db.execute("SELECT theme_id,theme_name FROM segments WHERE entry_id=?", (canonical_entry,)).fetchone()
            canonical_preview = db.execute("SELECT preview_json FROM entries WHERE id=?", (canonical_entry,)).fetchone()[0]
        self.assertEqual(tuple(canonical_segment), (target["id"], "户外"))
        self.assertIn('"theme":"户外"', canonical_preview)
        canonical_clean = next((self.root / "journals" / "cleaned").rglob(f"*{canonical_entry}.md"))
        self.assertIn("### 户外", canonical_clean.read_text(encoding="utf-8"))

        split = self.store.save_theme_review([
            {"action": "split", "source_theme_id": target["id"], "payload": {"themes": ["徒步", "露营"]}}
        ])
        result = self.store.apply_theme_changes([{"proposal_id": split["proposals"][0]["proposal_id"], "decision": "approved"}])
        new_theme_ids = result["results"][0]["theme_ids"]
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM themes WHERE id=?", (target["id"],)).fetchone()[0], "inactive")
            self.assertEqual(db.execute("SELECT theme_id FROM segments WHERE id=?", (target_segment["id"],)).fetchone()[0], target["id"])

        reassign = self.store.save_theme_review([
            {"action": "reassign_segment", "target_theme_id": new_theme_ids[0], "payload": {"segment_id": source_segment["id"]}}
        ])
        self.store.apply_theme_changes([{"proposal_id": reassign["proposals"][0]["proposal_id"], "decision": "approved"}])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT theme_id FROM segments WHERE id=?", (source_segment["id"],)).fetchone()[0], new_theme_ids[0])
            self.assertEqual(db.execute("SELECT theme_id FROM segments WHERE id=?", (target_segment["id"],)).fetchone()[0], target["id"])
        self.assertEqual(original_path.read_bytes(), original_bytes)
        self.assertEqual(clean_path.read_bytes(), clean_bytes)

    def test_goal_hierarchy_events_links_context_and_mirror(self):
        entry_id = self.confirm_entry("本周完成了两次跑步训练。", "2026-07-12", "运动")
        mirror_path = self.root / "memory" / "goals.md"
        mirror_before = mirror_path.read_bytes()
        rejected = self.store.goal_change_preview([
            {"action": "create", "payload": {"scope": "life", "title": "不应写入的目标"}}
        ])
        self.store.apply_goal_changes([{"proposal_id": rejected["proposals"][0]["proposal_id"], "decision": "rejected"}])
        self.assertEqual(mirror_path.read_bytes(), mirror_before)
        preview = self.store.goal_change_preview([
            {"action": "create", "ref": "life", "payload": {"scope": "life", "title": "保持长期健康", "priority": 5}},
            {"action": "create", "ref": "short", "parent_ref": "life", "payload": {"scope": "short_term", "title": "提升跑步耐力", "success_criteria": "连续跑步五公里"}},
            {"action": "create", "ref": "week", "parent_ref": "short", "payload": {"scope": "weekly", "title": "本周跑步三次"}},
        ])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM goals").fetchone()[0], 0)
        decisions = [{"proposal_id": item["proposal_id"], "decision": "approved"} for item in preview["proposals"]]
        applied = self.store.apply_goal_changes(decisions)
        goal_ids = {item["goal_id"] for item in applied["results"]}
        self.assertEqual(len(goal_ids), 3)
        goals = self.store.goal_context()["goals"]
        self.assertEqual(len(goals), 3)
        weekly_goal = next(item for item in goals if item["scope"] == "weekly")
        short_goal = next(item for item in goals if item["scope"] == "short_term")
        self.assertEqual(weekly_goal["parent_goal_id"], short_goal["id"])

        link = self.store.goal_change_preview([
            {"action": "link_entry", "goal_id": weekly_goal["id"], "payload": {"entry_id": entry_id, "relation": "progress", "evidence": "完成两次跑步"}}
        ])
        self.store.apply_goal_changes([{"proposal_id": link["proposals"][0]["proposal_id"], "decision": "approved"}])
        relevant = self.store.conversation_context("我的跑步目标进展如何？")
        self.assertTrue(relevant["has_context"])
        self.assertTrue(any(item["id"] == weekly_goal["id"] for item in relevant["goals"]))
        self.assertFalse(self.store.conversation_context("天气降雨和电影票房")["has_context"])

        pause = self.store.goal_change_preview([{"action": "pause", "goal_id": weekly_goal["id"], "evidence": ["需要休息"]}])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM goals WHERE id=?", (weekly_goal["id"],)).fetchone()[0], "active")
        self.store.apply_goal_changes([{"proposal_id": pause["proposals"][0]["proposal_id"], "decision": "approved"}])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM goals WHERE id=?", (weekly_goal["id"],)).fetchone()[0], "paused")
            self.assertGreaterEqual(db.execute("SELECT count(*) FROM goal_events WHERE goal_id=?", (weekly_goal["id"],)).fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT count(*) FROM goal_entry_links WHERE goal_id=?", (weekly_goal["id"],)).fetchone()[0], 1)
        mirror = (self.root / "memory" / "goals.md").read_text(encoding="utf-8")
        self.assertIn("本周跑步三次", mirror)
        self.assertIn("[paused]", mirror)
        weekly = self.store.weekly_context(datetime(2026, 7, 13, 1, 0, tzinfo=TZ))
        self.assertTrue(any(item["id"] == short_goal["id"] for item in weekly["goals"]))

    def test_initialize_migration_is_idempotent_and_preserves_journals(self):
        entry_id = self.confirm_entry("迁移不能改写日记。", "2026-06-01", "系统")
        original = next((self.root / "journals" / "originals").rglob(f"*{entry_id}.md"))
        cleaned = next((self.root / "journals" / "cleaned").rglob(f"*{entry_id}.md"))
        before = (original.read_bytes(), cleaned.read_bytes())
        self.store.initialize()
        self.store.initialize()
        self.assertEqual(before, (original.read_bytes(), cleaned.read_bytes()))
        with self.store.connect() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"theme_change_proposals", "goals", "goal_events", "goal_entry_links", "goal_change_proposals"}.issubset(tables))

    def test_project_skill_script_imports_from_any_working_directory(self):
        script = Path(__file__).parents[1] / ".agents" / "skills" / "record-life-journal" / "scripts" / "journal.py"
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(self.root), "init"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn('"ok": true', result.stdout)

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
        applied = self.store.mark_skill_revision(result["revision_id"], "applied", "tests passed")
        self.assertTrue(applied["commit"])
        with self.store.connect() as db:
            audit = db.execute("SELECT status,git_after_commit FROM skill_revisions WHERE id=?", (result["revision_id"],)).fetchone()
        self.assertEqual(tuple(audit), ("applied", applied["commit"]))
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertEqual(status, "")


if __name__ == "__main__":
    unittest.main()
