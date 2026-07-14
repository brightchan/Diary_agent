# Diary Agent

Diary Agent is a local-first personal journal and life-context system designed to be used through Codex. It captures the user's exact words, prepares a conservative cleaned preview, organizes entries with themes and tags, connects related experiences, tracks confirmed goals, and produces weekly reviews. Confirmed data is stored locally in SQLite and readable Markdown.

The project uses Python's standard library and Codex's reasoning. It does not require an OpenAI API key, add an OpenAI API client, or make external model calls from the application.

## Choose the section you need

- [For users: everyday use](#for-users-everyday-use) explains what to say to Codex.
- [Goals: life, long-term, short-term, and weekly](#goals-life-long-term-short-term-and-weekly) explains which goal types exist and how to add them.
- [For AI agents: operating protocol](#for-ai-agents-operating-protocol) defines the safe workflow and commands.
- [For maintainers: improving the system](#for-maintainers-improving-the-system) covers tests, backups, and Skill revisions.
- [Storage and repository map](#storage-and-repository-map) explains where data and code live.

## Quick start

Requirements:

- Python 3.11 or newer
- Git, for audited Skill-change snapshots
- Codex opened on this repository, for the intended conversation experience

From the repository root, initialize or migrate the local database:

```bash
python3 -m diary_agent.cli --root . init
```

Then open a Codex task on this folder and invoke `$record-life-journal`, or simply write a clear statement about your own experience. For example:

> I felt much calmer after walking home today, and I want to keep making space for that.

Codex should save the exact statement as a draft first, show a cleaned and organized preview, and wait for confirmation before finalizing it.

## For users: everyday use

### Record a diary entry

You can say:

> Record this in my diary: I had a difficult meeting today, but I handled the disagreement more calmly than before.

You do not always need to say “record this.” A standalone statement about your own experience, feeling, reflection, decision, or life status enters the diary workflow by default.

Direct questions, requests for information, and repository or coding commands are not captured as diary entries by default. If your wording could reasonably be either conversation or diary content, say explicitly whether you want it recorded.

The capture flow is:

1. Your exact text is saved immediately as a draft and preserved as the verbatim original.
2. Codex cleans only speech artifacts, repetition, punctuation, and obvious sentence boundaries.
3. Codex splits multiple ideas into ordered segments, gives each a primary theme, and may add cross-cutting tags.
4. When the entry is locally relevant to an Active goal, Codex may add a clearly labeled AI goal interpretation with evidence and concise feedback.
5. Codex may show uncertain terms, related older entries, and at most one optional reflection question.
6. You correct or remove any interpretation, confirm, skip the question, defer it, or decline the entry.
7. Only explicit confirmation creates the finalized cleaned journal and structured records.

Useful replies include:

- `Confirm this entry.`
- `Change the second paragraph to ... and show the preview again.`
- `The name is Wai Leong; update the uncertainty.`
- `Skip the reflection question and confirm the entry.`
- `Do not save this entry.`

Confirmed entries cannot be silently overwritten through the preview workflow. The original wording remains preserved even when the cleaned version or structured classification is corrected.

### Recall and search your history

Ask natural questions such as:

> What have I written about feeling stuck at work?

> When did I last mention restarting exercise?

> Compare how I described this decision before and now.

Search uses only confirmed local records. Codex should cite entry dates, separate evidence from inference, and stop retrieving when more context adds no useful information.

### Weekly journal review

The weekly workflow summarizes the previous Monday through Sunday when confirmed entries exist. It can cover:

- events and facts;
- feelings, insights, themes, and tags;
- related patterns or changed views from older entries;
- goal progress, blockers, and possible adjustments;
- unfinished threads and practical next-week actions;
- two to five optional reflection questions.

The weekly journal is also preview-first and requires confirmation. Goal changes and theme changes suggested by a weekly review are separate proposals; confirming the weekly journal does not apply them. After the review preview is generated, and again after confirmation or later corrections, the agent commits the complete repository state and pushes the current branch.

The intended schedule is Monday at 01:00 in `Asia/Singapore`. This repository does not run a background scheduler by itself. A Codex automation must be configured to invoke the weekly workflow.

### Organize themes and tags

Each journal segment has one primary theme and may have several cross-cutting tags. You can ask Codex to:

- create, rename, activate, or deactivate a theme;
- merge overlapping themes;
- split an overly broad theme;
- reassign one segment's primary theme;
- add or remove a tag from one segment.

Every change is shown as a proposal and requires an explicit decision per item. Deactivating or merging a theme changes structured retrieval behavior but does not rewrite the historical original or cleaned Markdown.

### Give feedback about the workflow

Tell Codex directly when the diary workflow is inconvenient or should behave differently:

> Workflow feedback: the preview is too long when an entry has only one simple idea.

Feedback is stored locally for the weekly Skill-improvement review. The intended review time is Monday at 02:00 in `Asia/Singapore`; it also needs a Codex automation if it should run automatically. A review may create a Skill-change proposal, but it cannot change the active Skill without explicit approval.

### Make a local backup

Ask Codex to back up the diary, or run:

```bash
python3 -m diary_agent.cli --root . backup
```

This creates a consistent SQLite backup and SHA-256 manifest under `data/backups/`. Journal Markdown is already stored separately and is intentionally tracked in Git with the main database.

## Goals: life, long-term, short-term, and weekly

The system supports four goal scopes:

| Scope | Purpose | Parent rule |
| --- | --- | --- |
| `life` | An open-ended life direction without a fixed completion horizon | Must be top-level |
| `long_term` | An outcome that spans multiple years | May belong to a life goal |
| `short_term` | An outcome intended to finish within one year | May belong to a life or long-term goal |
| `weekly` | A concrete focus for one week | May belong to any broader goal |

A parent must always be broader than its child. Goal status can be `active`, `completed`, `paused`, or `abandoned`.

### Add goals through conversation

State explicitly that you want a goal created. Diary Agent never converts an old journal statement into a goal merely because it sounds aspirational.

For a life goal:

> Add a life goal: Maintain lifelong physical and mental health. Priority 5. Success means I have sustainable exercise, sleep, and recovery habits.

For a connected multi-year long-term goal:

> Under “Maintain lifelong physical and mental health,” add a long-term goal: Establish sustainable endurance and strength over the next five years.

For a connected short-term goal intended to finish within one year:

> Under “Establish sustainable endurance and strength over the next five years,” add a short-term goal: Build enough running endurance to complete five kilometres comfortably by 30 September.

For a weekly goal:

> Under “Build enough running endurance,” add a weekly goal: Run three times this week. Success means three completed runs, including one easy long run.

Codex should show the proposed scope, title, parent, dates, priority, description, and success criteria. Reply with a precise decision such as:

> Approve all four goal proposals.

or:

> Approve the life goal, reject the other two, and do not apply anything else.

You can also ask to update, complete, pause, abandon, or reactivate a goal. Those actions follow the same preview-and-confirm rule.

### Record goal progress and blockers

During ordinary diary capture, Codex automatically checks only locally relevant Active goals. When the current entry contains evidence, the normal diary preview may include an AI interpretation labeled `progress`, `blocker`, `reflection`, or `related`, plus concise feedback. You can correct or remove it before confirming the entry. Confirmed interpretations remain analytical annotations: they do not change goal status, create goal events, or become authoritative goal evidence.

To promote a confirmed diary entry into authoritative goal evidence, explicitly ask Codex to link it:

> Link today's confirmed running entry to “Run three times this week” as progress. Evidence: completed the second run.

Supported evidence relations are `progress`, `blocker`, `reflection`, and `related`. Only confirmed entries can be linked.

To review goals, ask:

> Show my active goals and their recent evidence.

> How is my running goal progressing?

> Which weekly goals are paused?

SQLite is the authoritative source. [`memory/goals.md`](memory/goals.md) is a readable mirror regenerated only after confirmed goal changes; do not edit it by hand.

## For AI agents: operating protocol

### Read these instructions in order

1. [`AGENTS.md`](AGENTS.md) — repository-wide working agreement.
2. [`.agents/skills/record-life-journal/SKILL.md`](.agents/skills/record-life-journal/SKILL.md) — diary orchestration rules.
3. [`.agents/skills/record-life-journal/references/agent-protocol.md`](.agents/skills/record-life-journal/references/agent-protocol.md) — cleaner, classifier, continuity, theme, and goal payloads.
4. [`.agents/skills/record-life-journal/references/storage-schema.md`](.agents/skills/record-life-journal/references/storage-schema.md) — persistence and retrieval semantics.
5. [`.agents/skills/record-life-journal/references/skill-improvement.md`](.agents/skills/record-life-journal/references/skill-improvement.md) — only when processing workflow feedback or a Skill revision.

Use the project-local wrapper in agent workflows:

```bash
python3 .agents/skills/record-life-journal/scripts/journal.py --root . <command>
```

It delegates to the deterministic CLI while making imports work from different current directories. Commands emit JSON on stdout and structured errors on stderr.

### Decide whether a message is a diary capture

Treat an unqualified declarative message about the user's personal experience, feeling, reflection, decision, or life status as diary capture. Do not capture direct questions, repository/task commands, content-generation requests, or clearly non-diary messages by default. When genuinely ambiguous, continue the conversation instead of silently capturing.

This broad trigger does not remove the confirmation boundary. Never finalize a diary entry merely because capture was automatic.

### Entry pipeline

Create the draft before interpreting the user's wording:

```bash
python3 .agents/skills/record-life-journal/scripts/journal.py --root . \
  create-draft --text '<verbatim user input>'
```

Use the returned `entry_id` throughout the turn. Use its routing decision, journal context, and bounded `goal_context` instead of scanning the entire journal tree or all goals. When `goal_context.has_context` is false, skip goal interpretation.

Cleaning, classification, and continuity checks are always required. The deterministic cleaner is only a starting candidate:

```bash
python3 .agents/skills/record-life-journal/scripts/journal.py --root . \
  local-clean --text '<verbatim user input>'
```

Preserve facts, negation, intensity, uncertainty, voice, and chronology. Put any potentially meaning-changing correction in `uncertainties` instead of silently applying it.

After cleaning and classification, compare the entry only with goals in `goal_context`. Any match is AI-generated analysis based on current-entry evidence. It must not create or mutate a goal, goal event, or explicit goal-entry link.

Save the merged preview after presenting or correcting it:

```bash
python3 .agents/skills/record-life-journal/scripts/journal.py --root . save-preview \
  --entry-id '<uuid>' \
  --clean-text '<cleaned text>' \
  --segments '[{"text":"...","theme":"primary","tags":["cross-cutting"]}]' \
  --uncertainties '[]' --links '[]' --followups '[]' \
  --goal-interpretations '[{"goal_id":"...","relation":"progress","evidence":"...","interpretation":"...","feedback":"...","confidence":0.9}]'
```

Segments stay in narrative order. Each requires a primary `theme`; `tags` are optional, deduplicated, and must not repeat the primary theme. Goal interpretations are optional, use only Active goals, require evidence from this entry, and can be corrected or removed by saving the preview again. Ordinary entries may have at most one optional follow-up question.

Confirm only after the user explicitly approves the displayed version:

```bash
python3 .agents/skills/record-life-journal/scripts/journal.py --root . \
  confirm --entry-id '<uuid>'
```

Confirmation is idempotent. Report both returned Markdown paths. Never rewrite confirmed journals outside the core confirmation/export path.

Update a follow-up independently when the user answers, skips, or defers it:

```bash
python3 -m diary_agent.cli --root . update-followup \
  --followup-id '<uuid>' --status deferred --revisit-after '2026-08-01'
```

### Search and contextual retrieval

For journal recall:

```bash
python3 -m diary_agent.cli --root . search --query '<question>' --token-budget 1800
```

For goal-aware conversation context:

```bash
python3 -m diary_agent.cli --root . conversation-context \
  --query '<current question>' --token-budget 700
```

Use returned confirmed records only. Cite dates, distinguish evidence from inference, and do not replace relevance-based stopping with a fixed item count.

### Goal protocol

Never infer a goal from old diary prose. Convert an explicit user request into a preview first. A hierarchy can be proposed in one payload using `ref` and `parent_ref`:

```bash
python3 -m diary_agent.cli --root . goal-change-preview --changes '[
  {"action":"create","ref":"life","payload":{"scope":"life","title":"Maintain lifelong health","priority":5}},
  {"action":"create","ref":"long","parent_ref":"life","payload":{"scope":"long_term","title":"Establish sustainable fitness over the next five years"}},
  {"action":"create","ref":"short","parent_ref":"long","payload":{"scope":"short_term","title":"Build running endurance this year","success_criteria":"Run five kilometres comfortably"}},
  {"action":"create","parent_ref":"short","payload":{"scope":"weekly","title":"Run three times this week"}}
]'
```

Show every returned proposal to the user. Apply only their explicit per-item decisions:

```bash
python3 -m diary_agent.cli --root . apply-goal-changes --decisions '[
  {"proposal_id":"<returned uuid>","decision":"approved"},
  {"proposal_id":"<returned uuid>","decision":"rejected"}
]'
```

Supported actions are `create`, `update`, `complete`, `pause`, `abandon`, `activate`, and `link_entry`. Creation requires `scope` and `title`; optional fields are `parent_goal_id`, `description`, `priority`, `start_date`, `target_date`, and `success_criteria`. `link_entry` requires a confirmed entry and one of the supported evidence relations.

Retrieve goal state with:

```bash
python3 -m diary_agent.cli --root . goal-context --status active
python3 -m diary_agent.cli --root . goal-context --status all --query '<topic>'
```

After applied changes, the core regenerates `memory/goals.md`. Agents must not hand-edit the mirror.

### Theme-governance protocol

Start from compact evidence:

```bash
python3 -m diary_agent.cli --root . theme-review-context
```

Prepare proposals with `save-theme-review`, show each proposal and its evidence, then pass only explicit `approved` or `rejected` decisions to `apply-theme-changes`.

Supported actions are `create`, `activate`, `deactivate`, `rename`, `merge`, `split`, `reassign_segment`, `add_segment_tag`, and `remove_segment_tag`. A split creates active replacements and deactivates the source; it does not reclassify history. Historical reassignments and tag mutations need their own proposals.

### Weekly workflows

For the Monday 01:00 weekly journal:

```bash
python3 -m diary_agent.cli --root . weekly-context
```

Exit without semantic work when `has_content` is false. Otherwise use only the returned current entries, goals, historical connections, reflection candidate, and theme evidence. Each Active goal keeps explicit `weekly_evidence` separate from non-authoritative `weekly_interpretations`; summaries must preserve that distinction and must not silently promote interpretations. Create a weekly draft, show the review plus two to five optional questions, and require confirmation. Keep goal and theme mutations as separately confirmed proposals.

For the Monday 02:00 feedback review:

```bash
python3 -m diary_agent.cli --root . feedback-review-context
```

Exit when `has_feedback` is false. Otherwise follow `skill-improvement.md`; do not edit the active Skill merely because a proposal was created. Proposal generation commits and pushes the complete repository state.

### CLI command reference

| Command | Purpose |
| --- | --- |
| `init` | Create directories, schema, migrations, and missing memory files |
| `create-draft` | Store verbatim text and return routing, journal context, and locally relevant Active goals |
| `route` | Inspect deterministic delegation signals without creating an entry |
| `local-clean` | Produce a conservative cleaning candidate |
| `save-preview` | Store cleaned text, segments, uncertainties, links, follow-ups, and optional AI goal interpretations |
| `confirm` | Finalize a preview and export Markdown |
| `search` | Retrieve relevant confirmed journal records |
| `add-feedback` | Store workflow friction or a new requirement |
| `update-followup` | Mark a follow-up answered, skipped, or deferred |
| `weekly-context` | Build the previous week's evidence package |
| `theme-review-context` | Return theme states, usage, overlaps, and pending proposals |
| `save-theme-review` | Store theme-change proposals |
| `apply-theme-changes` | Apply explicit per-item theme decisions |
| `goal-change-preview` | Store goal-change proposals |
| `apply-goal-changes` | Apply explicit per-item goal decisions |
| `goal-context` | Retrieve goals by status and optional relevance query |
| `conversation-context` | Retrieve only active goals relevant to a question |
| `feedback-review-context` | Return unprocessed feedback from the last seven days |
| `propose-skill-revision` | Store a revision and take automatic pre-change Git snapshots |
| `mark-skill-revision` | Audit approval, application, rejection, or failure |
| `git-snapshot` | Checkpoint SQLite WAL and commit the complete local state |
| `git-publish` | Checkpoint SQLite WAL, commit the complete state, and push the current branch |
| `backup` | Create a consistent database backup and checksum |

Run `python3 -m diary_agent.cli --help` or append `--help` after a command for current arguments.

## For maintainers: improving the system

### Architecture constraints

- Keep the project local-first and standard-library-first.
- Do not add an OpenAI API client, API-key requirement, external model call, embeddings service, or vector database.
- Keep semantic judgment in Codex and use deterministic local routing, FTS5, indexes, and n-gram similarity for context selection.
- Treat SQLite as structured truth and Markdown as the human-readable record.
- Preserve verbatim originals.
- Track `data/diary.sqlite3` and all files under `journals/` in Git. Ignore only SQLite WAL/SHM sidecars and disposable caches.
- Preserve unrelated user changes in a dirty worktree.

### Validation

Run syntax and standard-library tests:

```bash
python3 -m py_compile diary_agent/*.py
python3 -m unittest discover -s tests -v
```

For the required repository pytest run, use the existing approved environment without modifying it:

```bash
/mnt/d/Project_PA/condaenv_host/bin/python -m pytest
```

Validate the Skill package before marking a Skill revision applied:

```bash
python3 /mnt/c/Users/chenj/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .agents/skills/record-life-journal
```

### Skill-change safety workflow

A change to the active diary Skill is more strictly governed than an ordinary code or documentation edit:

1. Capture the user's workflow feedback immediately with `add-feedback`.
2. Review unprocessed feedback and prepare the schema required by `skill-improvement.md`.
3. Run `propose-skill-revision`. This stores the proposal and automatically creates and pushes full-repository Git snapshots, including SQLite and journal Markdown.
4. Stop and obtain explicit user approval. A proposal alone is not authorization to edit the active Skill.
5. Implement only the approved scope.
6. Run pytest and `quick_validate.py`.
7. Mark the revision `applied` only after successful validation, or `failed` with the test summary. The result creates and pushes another audited Git snapshot plus its audit metadata.
8. If a push fails after the commits succeed, keep the commits and retry with `git-publish`. Do not create a duplicate proposal/result or report completion before the remote contains the final commit.

Do not use `git-snapshot` or `git-publish` casually: both stage the complete repository state, and `git-publish` also updates the remote branch.

## Storage and repository map

| Path | Role |
| --- | --- |
| `data/diary.sqlite3` | Authoritative structured diary, theme, goal, goal-interpretation, feedback, and revision data |
| `data/drafts/` | Temporary draft/preview state; removed after confirmation |
| `data/backups/` | SQLite backups and SHA-256 manifests |
| `journals/originals/YYYY/MM/` | Verbatim input, including draft/confirmed status |
| `journals/cleaned/YYYY/MM/` | Confirmed cleaned diary Markdown |
| `journals/weekly/YYYY/` | Confirmed weekly journal Markdown |
| `memory/goals.md` | Generated readable goal mirror; SQLite remains authoritative |
| `memory/workflow-feedback.md` | Readable workflow-feedback log |
| `memory/skill-proposal-*.json` | Stored Skill-improvement proposals |
| `memory/skill-change-history.md` | Skill revision result log |
| `diary_agent/core.py` | SQLite schema, storage, retrieval, governance, backup, and Git snapshot logic |
| `diary_agent/cli.py` | Deterministic command-line interface |
| `.agents/skills/record-life-journal/` | Codex Skill, protocols, schema guide, and wrapper |
| `tests/test_core.py` | End-to-end behavior and preservation tests |

The database uses SQLite WAL mode during normal work. WAL and SHM sidecars are disposable and ignored; the main database is checkpointed before an audited Git snapshot.

## Safety invariants

- Draft first, preview second, explicit confirmation last.
- Verbatim originals are never replaced by cleaned text.
- Confirmed journals are not silently rewritten by theme or goal governance.
- Goals are explicit user commitments, never inferred from older diary text.
- AI goal interpretations are current-entry annotations, not user-authored facts or authoritative goal evidence.
- Theme, tag, and goal mutations require per-item decisions.
- Follow-up questions are optional and never block confirmation.
- Weekly journal confirmation does not automatically apply goal, theme, or Skill changes.
- The application itself makes no external model call and requires no API key.
