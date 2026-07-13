# Diary Agent

A local-first Codex Skill for capturing spoken or typed personal journals, cleaning them conservatively, classifying evolving themes, connecting prior experiences, governing confirmed goals, asking optional follow-up questions, and storing confirmed records in SQLite plus Markdown.

## Initialize

```bash
python -m diary_agent.cli --root . init
```

Invoke `$record-life-journal` from a Codex task opened on this folder. The Skill stores verbatim drafts immediately, shows a cleaned and classified preview, and only finalizes an entry after confirmation.

## Schedules

- Monday 01:00 Asia/Singapore: prepare the previous week's journal when confirmed entries exist.
- Monday 02:00 Asia/Singapore: review new workflow feedback and prepare a Skill change proposal.

The proposal command automatically commits a complete Git snapshot, including the main SQLite database and all journal Markdown files. Applying a proposal still requires explicit confirmation.

## Theme and goal governance

All theme and goal mutations use preview-first, per-item confirmation:

```bash
python -m diary_agent.cli --root . theme-review-context
python -m diary_agent.cli --root . save-theme-review --changes changes.json
python -m diary_agent.cli --root . apply-theme-changes --decisions decisions.json

python -m diary_agent.cli --root . goal-change-preview --changes goals.json
python -m diary_agent.cli --root . apply-goal-changes --decisions decisions.json
python -m diary_agent.cli --root . goal-context
python -m diary_agent.cli --root . conversation-context --query 'current question'
```

Active themes are classification and theme-search candidates. Inactive themes keep all historical segments but are excluded from those defaults; entry full text remains searchable. Merged themes resolve to an Active canonical theme. Theme governance never silently rewrites confirmed Markdown.

SQLite is authoritative for life, short-term, and weekly goals. `memory/goals.md` is regenerated only after confirmed goal changes. Weekly context includes compact goal evidence and theme-review evidence, while applying those changes remains a separate confirmation step.
