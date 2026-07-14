# Diary Agent

A local-first Codex Skill for capturing spoken or typed personal journals, cleaning them conservatively, assigning primary themes and cross-cutting tags, connecting prior experiences, governing confirmed goals, asking optional follow-up questions, and storing confirmed records in SQLite plus Markdown.

## Initialize

```bash
python -m diary_agent.cli --root . init
```

Invoke `$record-life-journal` from a Codex task opened on this folder. The Skill stores verbatim drafts immediately, shows a cleaned and classified preview, and only finalizes an entry after confirmation.

A clear standalone statement about the user's personal experience, feeling, reflection, decision, or life status enters this same draft/preview workflow by default. Direct questions, repository/task commands, and clearly non-diary requests do not.

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

Each segment keeps one primary theme and may have multiple deduplicated tags. Active canonical primary themes and tags are searchable. Inactive themes keep all historical membership but are excluded from theme-driven search; entry full text remains searchable. Merged themes resolve to an Active canonical theme. Theme governance supports separately confirmed primary-theme reassignment and tag mutations, and never silently rewrites confirmed Markdown.

SQLite is authoritative for life, short-term, and weekly goals. `memory/goals.md` is regenerated only after confirmed goal changes. Weekly context includes compact goal evidence, theme-review evidence, and a bounded set of evidence-scored older related segments. An optional historical reflection prompt is considered only when that evidence is strong enough, while applying governance changes remains a separate confirmation step.
