# Storage schema

SQLite at `data/diary.sqlite3` is the structured source of truth.

- `entries`: raw and cleaned text, status, type, date, preview payload.
- `segments`: ordered text segments and themes.
- `themes`: stable themes, aliases, merge state.
- `entry_links`: evidence-backed relationships.
- `entities`: confirmed names and transcription aliases.
- `followups`: pending, answered, skipped, or deferred questions.
- `feedback_events`: workflow friction and new requirements.
- `skill_revisions`: Skill changes with Git snapshots.
- `agent_runs`: compact routing and size telemetry, never hidden reasoning.
- `entries_fts`: confirmed cleaned-text and theme index.

Markdown mirrors:

- `journals/originals/YYYY/MM/`: verbatim input.
- `journals/cleaned/YYYY/MM/`: confirmed cleaned diary.
- `journals/weekly/YYYY/`: confirmed weekly journal.

The main SQLite database and all journal Markdown files are intentionally Git-tracked. WAL and SHM sidecars are ignored.
