# Diary Agent

A local-first Codex Skill for capturing spoken or typed personal journals, cleaning them conservatively, classifying evolving themes, connecting prior experiences, asking optional follow-up questions, and storing confirmed records in SQLite plus Markdown.

## Initialize

```bash
python -m diary_agent.cli --root . init
```

Invoke `$record-life-journal` from a Codex task opened on this folder. The Skill stores verbatim drafts immediately, shows a cleaned and classified preview, and only finalizes an entry after confirmation.

## Schedules

- Monday 01:00 Asia/Singapore: prepare the previous week's journal when confirmed entries exist.
- Monday 02:00 Asia/Singapore: review new workflow feedback and prepare a Skill change proposal.

The proposal command automatically commits a complete Git snapshot, including the main SQLite database and all journal Markdown files. Applying a proposal still requires explicit confirmation.
