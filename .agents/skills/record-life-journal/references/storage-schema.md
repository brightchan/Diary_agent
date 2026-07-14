# Storage schema

SQLite at `data/diary.sqlite3` is the structured source of truth.

- `entries`: raw and cleaned text, status, type, date, preview payload.
- `segments`: ordered text segments and their primary themes.
- `segment_tags`: additive many-to-many segment theme/tag membership, including each primary theme for backward-compatible lookup.
- `themes`: stable themes with `active`, `inactive`, or `merged` status and canonical merge pointers.
- `theme_change_proposals`: preview, evidence, decision, and application audit for theme governance.
- `entry_links`: evidence-backed relationships.
- `entities`: confirmed names and transcription aliases.
- `followups`: pending, answered, skipped, or deferred questions.
- `goals`: confirmed life, short-term, and weekly goal hierarchy.
- `goal_events`: immutable goal creation, update, status, and evidence-link history.
- `goal_entry_links`: confirmed progress, blocker, reflection, or related evidence.
- `goal_change_proposals`: preview and per-item confirmation audit for goal changes.
- `feedback_events`: workflow friction and new requirements.
- `skill_revisions`: Skill changes with Git snapshots.
- `agent_runs`: compact routing and size telemetry, never hidden reasoning.
- `entries_fts`: confirmed cleaned-text plus every Active/canonical primary theme and tag. Inactive tags are removed from theme-driven matching without removing entry full text.

Markdown mirrors:

- `journals/originals/YYYY/MM/`: verbatim input.
- `journals/cleaned/YYYY/MM/`: confirmed cleaned diary.
- `journals/weekly/YYYY/`: confirmed weekly journal.

The main SQLite database and all journal Markdown files are intentionally Git-tracked. WAL and SHM sidecars are ignored.

Theme changes never rewrite verbatim originals or confirmed cleaned Markdown. `reassign_segment` changes only the explicitly approved structured primary theme; `add_segment_tag` and `remove_segment_tag` change only explicit structured tag membership. SQLite remains authoritative when a historical Markdown theme snapshot differs after governance.

`weekly-context` returns current-period entries, goal evidence, and a bounded `historical_connections` set of older segments with dates, IDs, scores, and evidence reasons. It excludes the current weekly period and returns `reflection_prompt_candidate: null` when evidence is insufficient.

Goal mirror:

- `memory/goals.md`: regenerated from SQLite only after confirmed goal changes; current hierarchy plus recent confirmed events.
