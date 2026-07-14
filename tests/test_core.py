from __future__ import annotations

import json
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

    def confirm_entry(self, text: str, date: str, theme: str = "生活", tags: list[str] | None = None) -> str:
        draft = self.store.create_draft(text, entry_date=date)
        self.store.save_preview(
            draft["entry_id"],
            text,
            [{"text": text, "theme": theme, "tags": tags or []}],
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

    def test_legacy_preview_and_multi_tag_search_and_markdown(self):
        legacy = self.store.create_draft("旧格式仍然有效。", entry_date="2026-05-01")
        preview = self.store.save_preview(legacy["entry_id"], "旧格式仍然有效。", [{"text": "旧格式仍然有效。", "theme": "系统"}])
        self.assertEqual(preview["preview"]["segments"][0]["tags"], [])
        self.store.confirm(legacy["entry_id"])

        draft = self.store.create_draft("今天慢跑三公里。", entry_date="2026-05-02")
        preview = self.store.save_preview(
            draft["entry_id"],
            "今天慢跑三公里。",
            [{"text": "今天慢跑三公里。", "theme": "运动", "tags": ["健康", "运动", "身心", "健康"]}],
        )
        self.assertEqual(preview["preview"]["segments"][0]["tags"], ["健康", "身心"])
        result = self.store.confirm(draft["entry_id"])
        with self.store.connect() as db:
            segment = db.execute("SELECT id FROM segments WHERE entry_id=?", (draft["entry_id"],)).fetchone()
            self.assertEqual(db.execute("SELECT count(*) FROM segment_tags WHERE segment_id=?", (segment["id"],)).fetchone()[0], 3)
        for query in ("运动", "健康", "身心"):
            matches = self.store.search(query, token_budget=500)
            match = next(item for item in matches if item["entry_id"] == draft["entry_id"])
            self.assertEqual(match["segments"][0]["theme"], "运动")
            self.assertEqual(match["segments"][0]["tags"], ["健康", "身心"])
        markdown = Path(result["clean_path"]).read_text(encoding="utf-8")
        self.assertIn("  - 健康", markdown)
        self.assertIn("Tags: 健康, 身心", markdown)

    def test_weekly_context_skips_empty_and_uses_previous_week(self):
        self.store.initialize()
        now = datetime(2026, 7, 13, 1, 0, tzinfo=TZ)
        self.assertFalse(self.store.weekly_context(now)["has_content"])
        self.confirm_entry("上周记录", "2026-07-12")
        context = self.store.weekly_context(now)
        self.assertEqual(context["period_start"], "2026-07-06")
        self.assertEqual(context["period_end"], "2026-07-12")
        self.assertEqual(len(context["entries"]), 1)

    def test_weekly_context_retrieves_bounded_older_segments_and_avoids_false_prompt(self):
        older = self.confirm_entry("跑步时总是呼吸急促，还没解决。", "2026-06-20", "运动", ["健康"])
        current = self.confirm_entry("本周跑步时仍然呼吸急促，计划调整节奏。", "2026-07-10", "运动", ["健康"])
        context = self.store.weekly_context(datetime(2026, 7, 13, 1, 0, tzinfo=TZ))
        self.assertTrue(context["historical_connections"])
        self.assertEqual(context["historical_connections"][0]["entry_id"], older)
        self.assertNotIn(current, {item["entry_id"] for item in context["historical_connections"]})
        self.assertTrue(context["historical_connections"][0]["evidence_reasons"])
        self.assertLessEqual(sum(len(item["text"]) for item in context["historical_connections"]), 1800)
        self.assertIsNotNone(context["reflection_prompt_candidate"])

        isolated = DiaryStore(self.root / "isolated")
        old_draft = isolated.create_draft("去年学习了水彩构图。", entry_date="2026-06-01")
        isolated.save_preview(old_draft["entry_id"], "去年学习了水彩构图。", [{"text": "去年学习了水彩构图。", "theme": "艺术"}])
        isolated.confirm(old_draft["entry_id"])
        new_draft = isolated.create_draft("本周服务器完成了备份。", entry_date="2026-07-10")
        isolated.save_preview(new_draft["entry_id"], "本周服务器完成了备份。", [{"text": "本周服务器完成了备份。", "theme": "系统"}])
        isolated.confirm(new_draft["entry_id"])
        unrelated = isolated.weekly_context(datetime(2026, 7, 13, 1, 0, tzinfo=TZ))
        self.assertEqual(unrelated["historical_connections"], [])
        self.assertIsNone(unrelated["reflection_prompt_candidate"])

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

    def test_tag_governance_uses_confirmation_and_canonical_active_names(self):
        entry_id = self.confirm_entry("晚饭后慢跑。", "2026-04-01", "生活", ["运动"])
        original = next((self.root / "journals" / "originals").rglob(f"*{entry_id}.md"))
        cleaned = next((self.root / "journals" / "cleaned").rglob(f"*{entry_id}.md"))
        journal_bytes = (original.read_bytes(), cleaned.read_bytes())
        with self.store.connect() as db:
            segment = db.execute("SELECT * FROM segments WHERE entry_id=?", (entry_id,)).fetchone()
            exercise = db.execute("SELECT * FROM themes WHERE name='运动'").fetchone()

        deactivate = self.store.save_theme_review([{"action": "deactivate", "source_theme_id": exercise["id"]}])
        self.store.apply_theme_changes([{"proposal_id": deactivate["proposals"][0]["proposal_id"], "decision": "approved"}])
        with self.store.connect() as db:
            self.assertNotIn("运动", db.execute("SELECT themes FROM entries_fts WHERE entry_id=?", (entry_id,)).fetchone()[0])
        blocked = self.store.create_draft("尝试复用停用标签。", entry_date="2026-04-02")
        self.store.save_preview(blocked["entry_id"], "尝试复用停用标签。", [{"text": "尝试复用停用标签。", "theme": "生活", "tags": ["运动"]}])
        with self.assertRaises(ValueError):
            self.store.confirm(blocked["entry_id"])

        activate = self.store.save_theme_review([{"action": "activate", "source_theme_id": exercise["id"]}])
        self.store.apply_theme_changes([{"proposal_id": activate["proposals"][0]["proposal_id"], "decision": "approved"}])
        create = self.store.save_theme_review([{"action": "create", "payload": {"name": "健身"}}])
        created = self.store.apply_theme_changes([{"proposal_id": create["proposals"][0]["proposal_id"], "decision": "approved"}])
        fitness_id = created["results"][0]["theme_ids"][0]
        merge = self.store.save_theme_review([{"action": "merge", "source_theme_id": exercise["id"], "target_theme_id": fitness_id}])
        self.store.apply_theme_changes([{"proposal_id": merge["proposals"][0]["proposal_id"], "decision": "approved"}])
        with self.store.connect() as db:
            self.assertIn("健身", db.execute("SELECT themes FROM entries_fts WHERE entry_id=?", (entry_id,)).fetchone()[0])
        canonical_tag_entry = self.confirm_entry("继续锻炼。", "2026-04-03", "生活", ["运动"])
        with self.store.connect() as db:
            canonical_preview = json.loads(db.execute("SELECT preview_json FROM entries WHERE id=?", (canonical_tag_entry,)).fetchone()[0])
        self.assertEqual(canonical_preview["segments"][0]["tags"], ["健身"])

        remove = self.store.save_theme_review([
            {"action": "remove_segment_tag", "source_theme_id": exercise["id"], "payload": {"segment_id": segment["id"]}}
        ])
        self.store.apply_theme_changes([{"proposal_id": remove["proposals"][0]["proposal_id"], "decision": "approved"}])
        with self.store.connect() as db:
            self.assertNotIn("健身", db.execute("SELECT themes FROM entries_fts WHERE entry_id=?", (entry_id,)).fetchone()[0])

        add = self.store.save_theme_review([
            {"action": "add_segment_tag", "target_theme_id": fitness_id, "payload": {"segment_id": segment["id"]}}
        ])
        self.store.apply_theme_changes([{"proposal_id": add["proposals"][0]["proposal_id"], "decision": "approved"}])
        with self.store.connect() as db:
            self.assertIn("健身", db.execute("SELECT themes FROM entries_fts WHERE entry_id=?", (entry_id,)).fetchone()[0])
        self.assertEqual(journal_bytes, (original.read_bytes(), cleaned.read_bytes()))

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
        with self.store.connect() as db:
            db.execute("DROP TABLE segment_tags")
            db.commit()
        self.store.initialize()
        self.store.initialize()
        self.assertEqual(before, (original.read_bytes(), cleaned.read_bytes()))
        with self.store.connect() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            backfilled = db.execute(
                """SELECT count(*) FROM segment_tags st JOIN segments s ON s.id=st.segment_id
                   WHERE s.entry_id=? AND st.theme_id=s.theme_id""",
                (entry_id,),
            ).fetchone()[0]
        self.assertTrue({"theme_change_proposals", "segment_tags", "goals", "goal_events", "goal_entry_links", "goal_change_proposals"}.issubset(tables))
        self.assertEqual(backfilled, 1)

    def test_default_personal_capture_guidance_and_no_external_semantic_dependency(self):
        project = Path(__file__).parents[1]
        agreement = (project / "AGENTS.md").read_text(encoding="utf-8")
        skill = (project / ".agents" / "skills" / "record-life-journal" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("unqualified declarative message", agreement)
        self.assertIn("Default personal-life capture", skill)
        package_text = "\n".join(path.read_text(encoding="utf-8") for path in (project / "diary_agent").glob("*.py"))
        for forbidden in ("OPENAI_API_KEY", "import openai", "embedding", "vector database"):
            self.assertNotIn(forbidden, package_text)

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
