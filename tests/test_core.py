from __future__ import annotations

import json
import sqlite3
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

    def create_goal(self, title: str, description: str = "", scope: str = "weekly") -> str:
        preview = self.store.goal_change_preview(
            [{"action": "create", "payload": {"scope": scope, "title": title, "description": description}}]
        )
        result = self.store.apply_goal_changes(
            [{"proposal_id": preview["proposals"][0]["proposal_id"], "decision": "approved"}]
        )
        return result["results"][0]["goal_id"]

    def decision_payload(self, status: str = "pending", review_date: str | None = "2026-07-12") -> dict:
        return {
            "status": status,
            "objective": "Choose whether to accept the new role without losing optionality.",
            "options": [
                {
                    "name": "Do nothing",
                    "is_do_nothing": True,
                    "facts": ["The current role remains available today."],
                    "assumptions": ["The current role will remain tolerable for another quarter."],
                    "reversible_consequences": ["I can revisit the choice next month."],
                    "irreversible_consequences": [],
                },
                {
                    "name": "Accept the new role",
                    "facts": ["The offer includes broader responsibility."],
                    "assumptions": ["The manager will support the transition."],
                    "reversible_consequences": ["The first-month onboarding plan can be tested."],
                    "irreversible_consequences": ["The current role may no longer be available."],
                },
            ],
            "opportunity_cost": {
                "facts": ["Time spent evaluating the offer delays other work."],
                "assumptions": ["The evaluation can be completed within a week."],
                "judgement": "The opportunity cost of waiting is meaningful but manageable.",
            },
            "likely_regret": {
                "one_year": "I may regret not testing the broader role.",
                "five_years": "I may regret optimizing only for short-term comfort.",
            },
            "assumptions": ["The role will create useful learning rather than only more workload."],
            "smallest_experiment": {
                "action": "Ask for a one-week shadowing conversation with the new team.",
                "uncertainty_reduced": "Whether the work and manager fit the actual objective.",
                "timebox": "One week",
                "success_signal": "Clear answers about scope, support, and first-quarter expectations.",
            },
            "recommendation": {
                "option": "Accept the new role",
                "facts": ["The role offers broader responsibility."],
                "assumptions": ["The support assumptions can be tested before committing fully."],
                "judgement": "Recommend accepting if the shadowing conversation confirms the support plan.",
            },
            "timeline": {
                "review_date": review_date,
                "due_date": "2026-07-15",
                "notes": "Revisit after the shadowing conversation.",
            },
        }

    def confirm_decision(self, text: str, date: str, status: str = "pending") -> tuple[str, dict]:
        draft = self.store.create_draft(text, entry_type="decision", entry_date=date)
        payload = self.decision_payload(status=status)
        preview = self.store.save_preview(
            draft["entry_id"],
            text,
            [{"text": text, "theme": "职业", "tags": ["艾名"]}],
            decision=payload,
        )
        result = self.store.confirm(draft["entry_id"])
        return draft["entry_id"], {"preview": preview, "result": result}

    def test_draft_preview_confirm_and_idempotency(self):
        draft = self.store.create_draft("嗯，今天我继续整理日记系统。另外也去跑步了。")
        self.assertEqual(
            draft["routing_decision"]["stages"],
            {"clean": True, "classify": True, "continuity": True, "goal_interpretation": True},
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
        legacy_result = self.store.confirm(legacy["entry_id"])
        self.assertNotIn("AI goal interpretation", Path(legacy_result["clean_path"]).read_text(encoding="utf-8"))

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

    def test_decision_preview_confirm_archive_search_and_weekly_reminder(self):
        entry_id, result = self.confirm_decision("我正在考虑是否接受新的工作机会。", "2026-07-01")
        self.assertEqual(result["preview"]["preview"]["decision"]["status"], "pending")
        with self.store.connect() as db:
            decision = db.execute("SELECT * FROM decisions WHERE entry_id=?", (entry_id,)).fetchone()
            self.assertEqual(decision["status"], "pending")
            self.assertEqual(decision["review_date"], "2026-07-12")
            self.assertEqual(db.execute("SELECT count(*) FROM segment_tags").fetchone()[0], 2)
        markdown = Path(result["result"]["clean_path"]).read_text(encoding="utf-8")
        self.assertIn("decision_status: pending", markdown)
        self.assertIn("### Recommendation", markdown)
        self.assertIn("Recommended option: Accept the new role", markdown)

        weekly = self.store.weekly_context(datetime(2026, 7, 13, 1, 0, tzinfo=TZ))
        self.assertTrue(weekly["has_content"])
        self.assertFalse(weekly["has_journal_content"])
        self.assertEqual(weekly["pending_decisions"][0]["reminder"], "overdue")
        self.assertEqual(weekly["decision_review"]["suggestions"][0]["decision_id"], decision["id"])
        self.assertTrue(any(item["entry_id"] == entry_id for item in self.store.search("new role")))

        proposed = self.store.decision_change_preview([{"action": "make", "decision_id": decision["id"]}])
        self.assertTrue(proposed["requires_confirmation"])
        applied = self.store.apply_decision_changes([{"proposal_id": proposed["proposals"][0]["proposal_id"], "decision": "approved"}])
        self.assertEqual(applied["results"][0]["status"], "applied")
        with self.store.connect() as db:
            made = db.execute("SELECT status,made_at,archived_at FROM decisions WHERE id=?", (decision["id"],)).fetchone()
            original = db.execute("SELECT raw_text FROM entries WHERE id=?", (entry_id,)).fetchone()[0]
        self.assertEqual(made["status"], "made")
        self.assertIsNotNone(made["archived_at"])
        self.assertEqual(original, "我正在考虑是否接受新的工作机会。")
        updated_markdown = Path(result["result"]["clean_path"]).read_text(encoding="utf-8")
        self.assertIn("decision_status: made", updated_markdown)
        self.assertIn("archived_at:", updated_markdown)

    def test_decision_requires_do_nothing_option_and_separates_judgement(self):
        draft = self.store.create_draft("是否换工作。", entry_type="decision")
        payload = self.decision_payload()
        payload["options"] = [{"name": "接受", "facts": [], "assumptions": []}, {"name": "拒绝"}]
        with self.assertRaisesRegex(ValueError, "do-nothing"):
            self.store.save_preview(draft["entry_id"], "是否换工作。", [{"text": "是否换工作。", "theme": "职业"}], decision=payload)

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

    def test_cleaning_preserves_non_speech_input_and_minimally_removes_fillers(self):
        original = "今天把该做的事情都做完了。。。这一点让我很安心。"
        self.assertEqual(self.store.conservative_clean(original), original)
        self.assertEqual(
            self.store.conservative_clean("嗯，今天把该做的事情做完了。。"),
            "今天把该做的事情做完了。",
        )
        self.assertEqual(self.store.route(original)["signals"]["cleaning_mode"], "preserve_verbatim")
        self.assertEqual(self.store.route("嗯，今天完成了。 ")["signals"]["cleaning_mode"], "minimal")

    def test_weekly_cleaning_style_profile_uses_confirmed_originals_and_reaches_new_drafts(self):
        texts = [
            "今天把积压的事情一项项处理完。过程没有什么戏剧性，但清空列表之后，脑子确实安静了不少。我没有刻意总结大道理，只是觉得这种踏实感值得记下来。",
            "下午重新梳理了接下来的安排，我还是习惯先写结论，再补充为什么这样决定，以及还有哪些不确定。这样写对我更直接，回头看时也能很快找到当时真正关心的问题。",
            "晚上回头看今天的记录，中文里夹一点 English 对我来说很自然，不需要为了所谓统一而改掉。有些词当下就是英文更顺手，强行换成中文反而不像我平时会说的话。",
        ]
        confirmed_ids = [
            self.confirm_entry(text, f"2026-07-{index + 1:02d}")
            for index, text in enumerate(texts)
        ]
        self.store.create_draft("这条还没有确认，不应进入文风样本。", entry_date="2026-07-04")
        weekly = self.store.create_draft("这是系统生成的周记，不应作为用户文风证据。", "weekly", entry_date="2026-07-05")
        self.store.save_preview(
            weekly["entry_id"],
            "这是系统生成的周记，不应作为用户文风证据。",
            [{"text": "这是系统生成的周记，不应作为用户文风证据。", "theme": "系统"}],
        )
        self.store.confirm(weekly["entry_id"])

        context = self.store.cleaning_style_context(char_budget=4000)
        self.assertTrue(context["has_new_samples"])
        self.assertTrue(context["ready_for_review"])
        self.assertEqual({item["id"] for item in context["samples"]}, set(confirmed_ids))
        self.assertLessEqual(
            sum(len(item["raw_text"]) + len(item["clean_text"] or "") for item in context["samples"]),
            context["char_budget"],
        )

        profile = {
            "summary": "偏好直接、紧凑的第一人称记录，保留自然的中英混用。",
            "preserve": ["先结论后原因的叙述顺序", "自然的中英混用", "克制的情绪表达"],
            "avoid": ["为了书面化而替换原词", "把短句合并成长句"],
            "observations": [
                {"trait": "叙述顺序", "evidence": "多个原始样本先写结果，再补充原因或感受。"},
                {"trait": "中英混用", "evidence": "原始样本自然使用 English，且明确表示无需统一。"},
            ],
        }
        saved = self.store.save_cleaning_style(profile, confirmed_ids)
        self.assertEqual(saved["sample_count"], 3)
        mirror = Path(saved["path"]).read_text(encoding="utf-8")
        self.assertIn("自然的中英混用", mirror)
        self.assertIn(confirmed_ids[0], mirror)

        new_draft = self.store.create_draft("今天继续按自己的方式记录。", entry_date="2026-07-06")
        self.assertEqual(new_draft["cleaning_style"]["profile"], profile)
        after = self.store.cleaning_style_context()
        self.assertFalse(after["has_new_samples"])
        self.assertFalse(after["ready_for_review"])

    def test_cleaning_style_rejects_insufficient_or_unconfirmed_evidence(self):
        profile = {
            "summary": "保持原文。",
            "preserve": [],
            "avoid": [],
            "observations": [],
        }
        drafts = [
            self.store.create_draft("尚未确认的样本。" * 20, entry_date=f"2026-07-0{index + 1}")["entry_id"]
            for index in range(3)
        ]
        with self.assertRaisesRegex(ValueError, "confirmed non-weekly"):
            self.store.save_cleaning_style(profile, drafts)

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
            {"action": "create", "ref": "life", "payload": {"scope": "life", "title": "保持终身健康方向", "priority": 5}},
            {"action": "create", "ref": "long", "parent_ref": "life", "payload": {"scope": "long_term", "title": "未来五年建立可持续体能"}},
            {"action": "create", "ref": "short", "parent_ref": "long", "payload": {"scope": "short_term", "title": "今年提升跑步耐力", "success_criteria": "连续跑步五公里"}},
            {"action": "create", "ref": "week", "parent_ref": "short", "payload": {"scope": "weekly", "title": "本周跑步三次"}},
        ])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM goals").fetchone()[0], 0)
        decisions = [{"proposal_id": item["proposal_id"], "decision": "approved"} for item in preview["proposals"]]
        applied = self.store.apply_goal_changes(decisions)
        goal_ids = {item["goal_id"] for item in applied["results"]}
        self.assertEqual(len(goal_ids), 4)
        goals = self.store.goal_context()["goals"]
        self.assertEqual(len(goals), 4)
        life_goal = next(item for item in goals if item["scope"] == "life")
        long_goal = next(item for item in goals if item["scope"] == "long_term")
        weekly_goal = next(item for item in goals if item["scope"] == "weekly")
        short_goal = next(item for item in goals if item["scope"] == "short_term")
        self.assertEqual(long_goal["parent_goal_id"], life_goal["id"])
        self.assertEqual(short_goal["parent_goal_id"], long_goal["id"])
        self.assertEqual(weekly_goal["parent_goal_id"], short_goal["id"])

        invalid = self.store.goal_change_preview([
            {"action": "create", "payload": {"scope": "long_term", "parent_goal_id": long_goal["id"], "title": "非法同层目标"}}
        ])
        with self.assertRaisesRegex(ValueError, "broader scope"):
            self.store.apply_goal_changes([
                {"proposal_id": invalid["proposals"][0]["proposal_id"], "decision": "approved"}
            ])

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
        self.assertIn("## Long-term", mirror)
        self.assertIn("未来五年建立可持续体能", mirror)
        self.assertIn("本周跑步三次", mirror)
        self.assertIn("[paused]", mirror)
        weekly = self.store.weekly_context(datetime(2026, 7, 13, 1, 0, tzinfo=TZ))
        self.assertTrue(any(item["id"] == short_goal["id"] for item in weekly["goals"]))

    def test_goal_scope_migration_adds_long_term_without_losing_history(self):
        self.store.paths.db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.store.paths.db) as db:
            db.executescript(
                """
                CREATE TABLE goals (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL CHECK(scope IN ('life','short_term','weekly')),
                    parent_goal_id TEXT REFERENCES goals(id),
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','paused','abandoned')),
                    priority INTEGER NOT NULL DEFAULT 0,
                    start_date TEXT,
                    target_date TEXT,
                    success_criteria TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE goal_events (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL REFERENCES goals(id),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                INSERT INTO goals VALUES (
                    'legacy-life', 'life', NULL, '既有人生目标', '', 'active', 0,
                    NULL, NULL, '', '2026-01-01T00:00:00+08:00', '2026-01-01T00:00:00+08:00'
                );
                INSERT INTO goal_events VALUES (
                    'legacy-event', 'legacy-life', 'created', '{}', '[]', '2026-01-01T00:00:00+08:00'
                );
                """
            )

        self.store.initialize()
        with self.store.connect() as db:
            goals_sql = db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='goals'"
            ).fetchone()[0]
            self.assertIn("'long_term'", goals_sql)
            self.assertEqual(db.execute("SELECT title FROM goals WHERE id='legacy-life'").fetchone()[0], "既有人生目标")
            self.assertEqual(db.execute("SELECT goal_id FROM goal_events WHERE id='legacy-event'").fetchone()[0], "legacy-life")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

        long_goal_id = self.create_goal("未来五年完成专业转型", scope="long_term")
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT scope FROM goals WHERE id=?", (long_goal_id,)).fetchone()[0], "long_term")

    def test_capture_returns_only_relevant_active_goal_context(self):
        no_goals = self.store.create_draft("今天完成了跑步训练。", entry_date="2026-07-07")
        self.assertFalse(no_goals["goal_context"]["has_context"])
        self.assertEqual(no_goals["goal_context"]["goals"], [])
        self.assertFalse(no_goals["routing_decision"]["delegate"]["goal_interpreter"])

        running_goal_id = self.create_goal("本周跑步三次", "提升跑步耐力和呼吸稳定性")
        reading_goal_id = self.create_goal("读完一本历史书", "整理阅读笔记")
        relevant = self.store.create_draft(
            "今天完成了第二次跑步训练，呼吸比上次稳定。",
            entry_date="2026-07-08",
        )
        selected_ids = {item["id"] for item in relevant["goal_context"]["goals"]}
        self.assertIn(running_goal_id, selected_ids)
        self.assertNotIn(reading_goal_id, selected_ids)
        self.assertTrue(relevant["routing_decision"]["delegate"]["goal_interpreter"])
        self.assertEqual(relevant["routing_decision"]["signals"]["relevant_goal_count"], 1)

    def test_goal_interpretation_validation_confirmation_and_weekly_context(self):
        active_goal_id = self.create_goal("本周跑步三次", "逐步恢复跑步训练")
        inactive_goal_id = self.create_goal("暂停的力量训练")
        pause = self.store.goal_change_preview([{"action": "pause", "goal_id": inactive_goal_id}])
        self.store.apply_goal_changes(
            [{"proposal_id": pause["proposals"][0]["proposal_id"], "decision": "approved"}]
        )
        text = "本周完成了第二次跑步训练，虽然很累但坚持下来了。"
        draft = self.store.create_draft(text, entry_date="2026-07-08")
        segments = [{"text": text, "theme": "运动"}]
        interpretation = {
            "goal_id": active_goal_id,
            "goal_title": "不应信任调用方提供的标题",
            "relation": "progress",
            "evidence": "完成了第二次跑步训练",
            "interpretation": "这是本周跑步次数的直接进展。",
            "feedback": "已推进目标；注意疲劳并安排恢复。",
            "confidence": 0.92,
        }

        invalid_payloads = [
            {**interpretation, "goal_id": "missing-goal"},
            {**interpretation, "goal_id": inactive_goal_id},
            {**interpretation, "relation": "achievement"},
            {**interpretation, "confidence": 1.1},
            {**interpretation, "confidence": "high"},
            {**interpretation, "evidence": "阅读了一本完全无关的历史书"},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.store.save_preview(draft["entry_id"], text, segments, goal_interpretations=[payload])
        with self.assertRaises(ValueError):
            self.store.save_preview(draft["entry_id"], text, segments, goal_interpretations={"bad": "shape"})
        with self.assertRaises(ValueError):
            self.store.save_preview(
                draft["entry_id"],
                text,
                segments,
                goal_interpretations=[{"goal_id": active_goal_id}],
            )

        first = self.store.save_preview(
            draft["entry_id"], text, segments, goal_interpretations=[interpretation]
        )
        normalized = first["preview"]["goal_interpretations"][0]
        self.assertEqual(normalized["goal_title"], "本周跑步三次")
        self.assertTrue(normalized["ai_generated"])
        self.assertFalse(normalized["authoritative"])
        removed = self.store.save_preview(
            draft["entry_id"], text, segments, goal_interpretations=[]
        )
        self.assertEqual(removed["preview"]["goal_interpretations"], [])
        corrected = {
            **interpretation,
            "feedback": "这是明确进展，同时应在下一次训练前恢复。",
        }
        self.store.save_preview(
            draft["entry_id"], text, segments, goal_interpretations=[corrected]
        )

        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM entry_goal_interpretations").fetchone()[0], 0)
            event_count = db.execute("SELECT count(*) FROM goal_events").fetchone()[0]
            link_count = db.execute("SELECT count(*) FROM goal_entry_links").fetchone()[0]
            statuses = dict(db.execute("SELECT id,status FROM goals").fetchall())
        result = self.store.confirm(draft["entry_id"])
        clean_markdown = Path(result["clean_path"]).read_text(encoding="utf-8")
        self.assertIn("AI goal interpretation", clean_markdown)
        self.assertIn("并非用户原话或权威目标记录", clean_markdown)
        self.assertIn(corrected["feedback"], clean_markdown)
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM entry_goal_interpretations").fetchone()
            entry = db.execute("SELECT raw_text,clean_text FROM entries WHERE id=?", (draft["entry_id"],)).fetchone()
            self.assertEqual(row["goal_id"], active_goal_id)
            self.assertEqual(row["feedback"], corrected["feedback"])
            self.assertEqual(tuple(entry), (text, text))
            self.assertEqual(db.execute("SELECT count(*) FROM goal_events").fetchone()[0], event_count)
            self.assertEqual(db.execute("SELECT count(*) FROM goal_entry_links").fetchone()[0], link_count)
            self.assertEqual(dict(db.execute("SELECT id,status FROM goals").fetchall()), statuses)

        weekly = self.store.weekly_context(datetime(2026, 7, 13, 1, 0, tzinfo=TZ))
        active_goal = next(item for item in weekly["goals"] if item["id"] == active_goal_id)
        self.assertEqual(active_goal["weekly_evidence"], [])
        self.assertEqual(len(active_goal["weekly_interpretations"]), 1)
        weekly_interpretation = active_goal["weekly_interpretations"][0]
        self.assertEqual(weekly_interpretation["entry_id"], draft["entry_id"])
        self.assertEqual(weekly_interpretation["source_type"], "ai_goal_interpretation")
        self.assertFalse(weekly_interpretation["authoritative"])

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
        self.assertTrue({"theme_change_proposals", "segment_tags", "goals", "goal_events", "goal_entry_links", "entry_goal_interpretations", "goal_change_proposals", "cleaning_style_profiles", "decisions", "decision_change_proposals"}.issubset(tables))
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

    def test_weekly_review_publish_and_skill_revision_reach_remote(self):
        remote_temp = tempfile.TemporaryDirectory()
        self.addCleanup(remote_temp.cleanup)
        remote = Path(remote_temp.name) / "diary.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=self.root, check=True, capture_output=True)

        weekly = self.store.create_draft("本周完成了日记发布流程。", "weekly", entry_date="2026-07-12")
        self.store.save_preview(
            weekly["entry_id"],
            "本周完成了日记发布流程。",
            [{"text": "本周完成了日记发布流程。", "theme": "系统"}],
        )
        published = self.store.git_publish("chore(diary): publish weekly review 2026-07-12")
        self.assertEqual(published["commit"], published["push"]["commit"])

        feedback = self.store.add_feedback("希望自动提交")
        result = self.store.propose_skill_revision(
            {"feedback_ids": [feedback["feedback_id"]], "summary": "自动提交"}
        )
        self.assertTrue(result["snapshot_commit"])
        self.assertEqual(result["metadata_commit"], result["push"]["commit"])
        tracked = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("data/diary.sqlite3", tracked)
        self.assertIn("journals/originals/2026/07/", tracked)
        applied = self.store.mark_skill_revision(result["revision_id"], "applied", "tests passed")
        self.assertTrue(applied["commit"])
        self.assertEqual(applied["metadata_commit"], applied["push"]["commit"])
        with self.store.connect() as db:
            audit = db.execute("SELECT status,git_after_commit FROM skill_revisions WHERE id=?", (result["revision_id"],)).fetchone()
        self.assertEqual(tuple(audit), ("applied", applied["commit"]))
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()
        remote_head = subprocess.run(
            ["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{branch}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(remote_head, applied["metadata_commit"])
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertEqual(status, "")

    def test_git_publish_requires_remote(self):
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        self.store.initialize()
        with self.assertRaisesRegex(RuntimeError, "no Git remote"):
            self.store.git_publish("chore(diary): publish without remote")


if __name__ == "__main__":
    unittest.main()
