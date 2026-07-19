# Storage schema

SQLite at `data/diary.sqlite3` is the structured source of truth.

- `entries`: raw and cleaned text, status, whole-input type, date, preview payload. Each user input is exactly one `diary`, `thought`, or `decision`; subjects remain themes/tags. `weekly` is reserved for generated reviews.
- `segments`: ordered text segments and their primary themes.
- `segment_tags`: additive many-to-many segment theme/tag membership, including each primary theme for backward-compatible lookup.
- `themes`: stable themes with `active`, `inactive`, or `merged` status and canonical merge pointers.
- `theme_change_proposals`: preview, evidence, decision, and application audit for theme governance.
- `entry_links`: evidence-backed relationships.
- `entities`: confirmed names and transcription aliases.
- `followups`: pending, answered, skipped, or deferred questions.
- `goals`: confirmed life, multi-year long-term, within-one-year short-term, and weekly goal hierarchy.
- `goal_events`: immutable goal creation, update, status, and evidence-link history.
- `goal_entry_links`: confirmed progress, blocker, reflection, or related evidence.
- `entry_goal_interpretations`: AI-generated, current-entry evidence annotations persisted only with diary confirmation; separate from authoritative goal links and events.
- `entry_agent_feedback`: optional one-to-one, non-authoritative Agent feedback for a confirmed diary, thought, or decision; stores the feedback body, active/passive trigger, bounded confirmed-entry evidence, and audit timestamps separately from user text.
- `goal_change_proposals`: preview and per-item confirmation audit for goal changes.
- `decisions`: structured pending or made decisions linked one-to-one with a confirmed `decision` entry; includes the analysis template, timeline, and archive timestamps.
- `decision_change_proposals`: explicit preview and per-item confirmation audit for updating, making, or reopening decisions.
- `feedback_events`: workflow friction and new requirements.
- `skill_revisions`: Skill changes with Git snapshots.
- `agent_runs`: compact routing and size telemetry, never hidden reasoning.
- `entries_fts`: confirmed cleaned-text plus every Active/canonical primary theme and tag. Agent feedback is deliberately excluded so it cannot be mistaken for the user's historical view. Decision analysis remains available through decision-aware local retrieval. Inactive tags are removed from theme-driven matching without removing entry full text.
- `cleaning_style_profiles`: compact, evidence-bounded cleaning-style profiles derived from confirmed non-weekly originals; source entry ids and evidence dates are retained for audit.

Markdown mirrors:

- `journals/originals/YYYY/MM/`: verbatim input.
- `journals/cleaned/YYYY/MM/`: confirmed cleaned diary, thought, or decision, with an independent `Agent feedback` section when confirmed.
- `memory/cleaning-style.md`: latest human-readable preservation profile; SQLite profile history remains authoritative.
- `journals/weekly/YYYY/`: confirmed weekly journal.

The main SQLite database and all journal Markdown files are intentionally Git-tracked. WAL and SHM sidecars are ignored.

Theme changes never rewrite verbatim originals or confirmed cleaned Markdown. `reassign_segment` changes only the explicitly approved structured primary theme; `add_segment_tag` and `remove_segment_tag` change only explicit structured tag membership. SQLite remains authoritative when a historical Markdown theme snapshot differs after governance.

`weekly-context` returns current-period `entries` for compatibility plus separate `diary_entries` and `thought_entries`, each entry's optional `agent_feedback` as a separate non-authoritative field, Active goals with separate `weekly_evidence` and non-authoritative `weekly_interpretations`, timeline-aware `pending_decisions` plus `decision_review` suggestions, and a bounded `historical_connections` set of older segments with dates, IDs, scores, and evidence reasons. It excludes the current weekly period and returns `reflection_prompt_candidate: null` when evidence is insufficient. Agent feedback and weekly interpretation records never mutate user text, goal state, or decision facts.

Goal mirror:

- `memory/goals.md`: regenerated from SQLite only after confirmed goal changes; current hierarchy plus recent confirmed events.
- Goal breadth is `life -> long_term -> short_term -> weekly`: life goals are open-ended directions, long-term goals span multiple years, short-term goals are intended to finish within one year, and weekly goals cover one week. Parents must be broader than children, but intermediate levels are optional.
