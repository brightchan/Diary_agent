from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .core import DiaryStore, TZ


def load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Local deterministic core for the Codex diary skill")
    root.add_argument("--root", default=".", help="Diary project root")
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("init")

    create = commands.add_parser("create-draft")
    create.add_argument("--text", required=True)
    create.add_argument("--type", default="diary", choices=["diary", "weekly", "thought", "decision"])
    create.add_argument("--source", default="codex")
    create.add_argument("--date")

    route = commands.add_parser("route")
    route.add_argument("--text", required=True)

    clean = commands.add_parser("local-clean")
    clean.add_argument("--text", required=True)

    style_context = commands.add_parser("cleaning-style-context")
    style_context.add_argument("--char-budget", type=int, default=8000)

    style_save = commands.add_parser("save-cleaning-style")
    style_save.add_argument("--profile", required=True, help="JSON string or file")
    style_save.add_argument("--source-entry-ids", required=True, help="JSON string or file")

    preview = commands.add_parser("save-preview")
    preview.add_argument("--entry-id", required=True)
    preview.add_argument("--entry-type", choices=["diary", "thought", "decision"])
    preview.add_argument("--clean-text", required=True)
    preview.add_argument("--segments", required=True, help="JSON string or file")
    preview.add_argument("--uncertainties")
    preview.add_argument("--links")
    preview.add_argument("--followups")
    preview.add_argument(
        "--goal-interpretations",
        help="JSON string or file with AI goal interpretations shown in this preview",
    )
    preview.add_argument(
        "--decision",
        help="JSON string or file with the structured decision analysis for a decision entry",
    )
    preview.add_argument(
        "--agent-feedback",
        help="JSON string or file with optional non-authoritative Agent feedback",
    )

    confirm = commands.add_parser("confirm")
    confirm.add_argument("--entry-id", required=True)

    search = commands.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--token-budget", type=int, default=1800)
    search.add_argument("--type", default="all", choices=["all", "diary", "thought", "decision", "weekly"])

    feedback = commands.add_parser("add-feedback")
    feedback.add_argument("--text", required=True)
    feedback.add_argument("--kind", default="inconvenience")
    feedback.add_argument("--entry-id")

    followup = commands.add_parser("update-followup")
    followup.add_argument("--followup-id", required=True)
    followup.add_argument("--status", required=True, choices=["answered", "skipped", "deferred"])
    followup.add_argument("--answer")
    followup.add_argument("--revisit-after")

    weekly = commands.add_parser("weekly-context")
    weekly.add_argument("--now", help="ISO datetime for testing")

    theme_context = commands.add_parser("theme-review-context")
    theme_context.add_argument("--now", help="ISO datetime for testing")

    theme_review = commands.add_parser("save-theme-review")
    theme_review.add_argument("--changes", required=True, help="JSON string or file")

    theme_apply = commands.add_parser("apply-theme-changes")
    theme_apply.add_argument("--decisions", required=True, help="JSON string or file")

    goal_preview = commands.add_parser("goal-change-preview")
    goal_preview.add_argument("--changes", required=True, help="JSON string or file")

    goal_apply = commands.add_parser("apply-goal-changes")
    goal_apply.add_argument("--decisions", required=True, help="JSON string or file")

    goal_context = commands.add_parser("goal-context")
    goal_context.add_argument("--query")
    goal_context.add_argument("--status", default="active", choices=["active", "completed", "paused", "abandoned", "all"])

    decision_review = commands.add_parser("decision-review-context")
    decision_review.add_argument("--now", help="ISO datetime for testing")

    decision_context = commands.add_parser("decision-context")
    decision_context.add_argument("--query")
    decision_context.add_argument("--status", default="pending", choices=["pending", "made", "all"])

    decision_preview = commands.add_parser("decision-change-preview")
    decision_preview.add_argument("--changes", required=True, help="JSON string or file")

    decision_apply = commands.add_parser("apply-decision-changes")
    decision_apply.add_argument("--decisions", required=True, help="JSON string or file")

    conversation = commands.add_parser("conversation-context")
    conversation.add_argument("--query", required=True)
    conversation.add_argument("--token-budget", type=int, default=700)

    review = commands.add_parser("feedback-review-context")
    review.add_argument("--now", help="ISO datetime for testing")

    propose = commands.add_parser("propose-skill-revision")
    propose.add_argument("--proposal", required=True, help="JSON string or file")

    revision = commands.add_parser("mark-skill-revision")
    revision.add_argument("--revision-id", required=True)
    revision.add_argument("--status", required=True, choices=["approved", "applied", "rejected", "failed"])
    revision.add_argument("--test-summary", default="")

    snapshot = commands.add_parser("git-snapshot")
    snapshot.add_argument("--message", required=True)

    publish = commands.add_parser("git-publish")
    publish.add_argument("--message", required=True)

    commands.add_parser("backup")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = DiaryStore(args.root)
    try:
        if args.command == "init":
            result = store.initialize()
        elif args.command == "create-draft":
            result = store.create_draft(args.text, args.type, args.source, args.date)
        elif args.command == "route":
            result = store.route(args.text)
        elif args.command == "local-clean":
            result = {"clean_text": store.conservative_clean(args.text)}
        elif args.command == "cleaning-style-context":
            result = store.cleaning_style_context(args.char_budget)
        elif args.command == "save-cleaning-style":
            result = store.save_cleaning_style(
                load_json(args.profile, {}),
                load_json(args.source_entry_ids, []),
            )
        elif args.command == "save-preview":
            result = store.save_preview(
                args.entry_id,
                args.clean_text,
                load_json(args.segments, []),
                load_json(args.uncertainties, []),
                load_json(args.links, []),
                load_json(args.followups, []),
                load_json(args.goal_interpretations, []),
                load_json(args.decision, None),
                args.entry_type,
                load_json(args.agent_feedback, None),
            )
        elif args.command == "confirm":
            result = store.confirm(args.entry_id)
        elif args.command == "search":
            result = store.search(args.query, args.token_budget, None if args.type == "all" else args.type)
        elif args.command == "add-feedback":
            result = store.add_feedback(args.text, args.kind, args.entry_id)
        elif args.command == "update-followup":
            result = store.update_followup(args.followup_id, args.status, args.answer, args.revisit_after)
        elif args.command == "weekly-context":
            moment = datetime.fromisoformat(args.now).replace(tzinfo=TZ) if args.now else None
            result = store.weekly_context(moment)
        elif args.command == "theme-review-context":
            moment = datetime.fromisoformat(args.now).replace(tzinfo=TZ) if args.now else None
            result = store.theme_review_context(moment)
        elif args.command == "save-theme-review":
            result = store.save_theme_review(load_json(args.changes, []))
        elif args.command == "apply-theme-changes":
            result = store.apply_theme_changes(load_json(args.decisions, []))
        elif args.command == "goal-change-preview":
            result = store.goal_change_preview(load_json(args.changes, []))
        elif args.command == "apply-goal-changes":
            result = store.apply_goal_changes(load_json(args.decisions, []))
        elif args.command == "goal-context":
            result = store.goal_context(args.query, args.status)
        elif args.command == "decision-review-context":
            moment = datetime.fromisoformat(args.now).replace(tzinfo=TZ) if args.now else None
            result = store.decision_review_context(moment)
        elif args.command == "decision-context":
            result = store.decision_context(args.query, args.status)
        elif args.command == "decision-change-preview":
            result = store.decision_change_preview(load_json(args.changes, []))
        elif args.command == "apply-decision-changes":
            result = store.apply_decision_changes(load_json(args.decisions, []))
        elif args.command == "conversation-context":
            result = store.conversation_context(args.query, args.token_budget)
        elif args.command == "feedback-review-context":
            moment = datetime.fromisoformat(args.now).replace(tzinfo=TZ) if args.now else None
            result = store.feedback_review_context(moment)
        elif args.command == "propose-skill-revision":
            result = store.propose_skill_revision(load_json(args.proposal, {}))
        elif args.command == "mark-skill-revision":
            result = store.mark_skill_revision(args.revision_id, args.status, args.test_summary)
        elif args.command == "git-snapshot":
            result = {"commit": store.git_snapshot(args.message)}
        elif args.command == "git-publish":
            result = store.git_publish(args.message)
        elif args.command == "backup":
            result = store.backup()
        else:
            raise ValueError(args.command)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
