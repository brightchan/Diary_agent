# Diary Agent

Diary Agent is a local-first journal, thought, decision, and life-context system designed to be used through Codex. It captures the user's exact words, classifies each complete recordable user input as a diary entry, thought, or decision, prepares a conservative cleaned preview, stores optional Agent feedback separately from the user's voice, organizes entries with themes and tags, connects related records, tracks confirmed goals, and produces weekly reviews. Confirmed data is stored locally in SQLite and readable Markdown.

The project uses Python's standard library and Codex's reasoning. It does not require an OpenAI API key, add an OpenAI API client, or make external model calls from the application.

## Choose the section you need

- [For users: everyday use](#for-users-everyday-use) explains what to say to Codex.
- [Diary entries, thoughts, and decisions](#record-a-thought) explains the whole-input distinction.
- [Agent feedback](#keep-agent-feedback-with-an-entry) explains active thought/decision feedback and passive diary feedback.
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

You do not always need to say “record this.” A standalone statement about your own experience, feeling, reflection, decision, life status, or an idea you want to preserve enters the capture workflow by default. Each complete recordable user input receives one previewed type: `diary`, `thought`, or `decision`.

Direct questions, requests for information, and repository or coding commands are not captured as diary entries by default. If your wording could reasonably be either conversation or diary content, say explicitly whether you want it recorded.

The capture flow is:

1. Your exact text is saved immediately as a draft and preserved as the verbatim original.
2. Codex classifies the complete input as `diary`, `thought`, or `decision`; this is one type for the whole input, not one type per segment. `weekly` is reserved for generated reviews.
3. Codex cleans only speech artifacts, repetition, punctuation, and obvious sentence boundaries.
4. Codex splits multiple ideas into ordered segments, gives each a primary theme, and may add cross-cutting tags.
5. Codex may prepare a separate Agent feedback column: diary feedback is only produced when you ask; thought and decision feedback is active by default unless you skip it.
6. When the entry is locally relevant to an Active goal, Codex may add a clearly labeled AI goal interpretation with evidence and concise feedback.
7. Codex shows the proposed type, cleaned text, themes, Agent feedback, uncertain terms, related older entries, and at most one optional reflection question.
8. You correct the type or any interpretation, confirm, skip the question, defer it, or decline the entry.
9. Only explicit confirmation creates the finalized cleaned journal and structured records.

Useful replies include:

- `Confirm this entry.`
- `Change the second paragraph to ... and show the preview again.`
- `The name is Wai Leong; update the uncertainty.`
- `Skip the reflection question and confirm the entry.`
- `Do not save this entry.`

Confirmed entries cannot be silently overwritten through the preview workflow. The original wording remains preserved even when the cleaned version or structured classification is corrected.

### Record a thought

Use a thought for an idea that should remain useful beyond the event that prompted it, for example:

> Record this as a thought: cell fate may be easier to model as an attractor state than as a fixed label.

> 记录一个想法：人的能力差异可能更多来自如何调用自己的认知能力，而不只是智商本身。

The type applies to the user's entire input. One input is never split into records with different types. Ordered segments can still carry different themes and tags.

| Type | Use it when the input is mainly about | Example |
| --- | --- | --- |
| `diary` | lived events, feelings, personal status, or a time-specific reflection | “今天开会后，我意识到自己总在回避冲突。” |
| `thought` | a proposition, hypothesis, conceptual question, model, interpretation, or reusable insight | “冲突回避可能是一种对关系损失的风险估计。” |
| `decision` | a meaningful pending or made choice between options | “我需要决定是否接受新的职位，下周复盘。” |

For mixed input, Codex selects the dominant purpose of the complete message and shows the proposed type in the preview. You can reply `Change the type to thought`, `这条应该是日记`, or `把这条作为一个待决定事项` before confirmation. An explicit type in your request takes precedence. A decision preview additionally requires the structured analysis described below.

Physics, biology, life, philosophy, and similar subjects are themes or tags, not entry types. For example, a record can have `type: thought`, primary theme `生物学`, and tags such as `细胞命运` and `复杂系统`.

Direct questions and requests for information remain conversation unless you explicitly ask to preserve them. `weekly` remains a system-generated special record type rather than a user-input type.

### Keep Agent feedback with an entry

Agent feedback is stored in its own field and Markdown section. It never becomes part of your verbatim original, cleaned wording, goal evidence, or decision facts.

- For a `diary`, Codex does not volunteer advice. Ask `给这条日记一点反馈` to add passive feedback of at most 200 Chinese characters.
- For a `thought`, Codex normally gives 100-200 Chinese characters of active feedback. When evidence supports it, the response includes both support and counterargument, strengths and limits, applicability boundaries, and a close connection to evidence or a confirmed prior thought.
- For a `decision`, Codex normally gives active feedback of at most 200 Chinese characters based primarily on related confirmed decisions and thoughts. It presents reasons for and risks against the direction and gives conditional advice without replacing the full decision analysis.

After discussing a thought, you can preserve the original, specify different wording, ask Codex to synthesize both sides, or decline storage. A synthesis becomes your stored thought only after you choose it and approve the new preview. `直接入库` skips synthesis but still requires preview confirmation; `不入库` prevents confirmation. You can also say `不要 Agent 反馈` for any entry.

### Track a decision

Say explicitly that you want a choice tracked as a decision, for example:

> Track this as a pending decision: whether I should accept the new role. Revisit it next week.

Decision entries use the same themes and tags as diary entries, but also keep a structured analysis. The preview includes the actual objective, options including doing nothing, reversible and irreversible consequences, opportunity cost, likely regret in one or five years, assumptions that could be wrong, the smallest experiment that would reduce uncertainty, and one recommendation. Facts, assumptions, and the agent's judgement are shown separately. The separate Agent-feedback field is the short, history-aware response; it does not replace this full analysis.

If you provide only the choice or objective, Codex fills the missing analysis from your wording and bounded local context, labels those additions as agent analysis, and asks you to confirm the completed preview. A pending decision stays open for future consideration; a made decision is archived for future reference. You can later ask to update, make, or reopen a decision, but those changes are explicit proposals and never rewrite the original wording.

Give a decision a review date or due date when timing matters. Weekly review will surface overdue and upcoming pending decisions with a suggested next action: finalize, defer with a new date, run the smallest experiment, or leave it pending.

### Recall and search your history

Ask natural questions such as:

> What have I written about feeling stuck at work?

> When did I last mention restarting exercise?

> Compare how I described this decision before and now.

You can limit recall to one record type:

> Search only my thoughts about intelligence and learning.

```bash
python3 -m diary_agent.cli --root . search --query 'intelligence and learning' --type thought
python3 -m diary_agent.cli --root . search --query 'work meeting' --type diary
```

Search uses only confirmed local records. Codex should cite entry dates, separate evidence from inference, and stop retrieving when more context adds no useful information.
Returned Agent feedback is labeled separately and is not used as evidence of what you previously believed. Default FTS matching continues to index your cleaned text and themes, not Agent feedback.

### Weekly journal review

The weekly workflow summarizes the previous Monday through Sunday when confirmed entries exist. It can cover:

- diary events, facts, feelings, and time-specific reflections;
- thoughts, hypotheses, conceptual changes, and questions worth developing;
- themes and tags across both record types;
- related patterns or changed views from older entries;
- goal progress, blockers, and possible adjustments;
- unfinished threads and practical next-week actions;
- pending decisions with timeline-aware reminders and structured recommendations;
- two to five optional reflection questions.

The weekly journal is also preview-first and requires confirmation. Goal changes and theme changes suggested by a weekly review are separate proposals; confirming the weekly journal does not apply them. After the review preview is generated, and again after confirmation or later corrections, the agent commits the complete repository state and pushes the current branch.

The intended schedule is Monday at 01:00 in `Asia/Singapore`. This repository does not run a background scheduler by itself. A Codex automation must be configured to invoke the weekly workflow.

### Organize themes and tags

Each diary, thought, or decision segment has one primary theme and may have several cross-cutting tags. You can ask Codex to:

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

During diary, thought, or decision capture, Codex automatically checks only locally relevant Active goals. When the current entry contains evidence, the normal preview may include an AI interpretation labeled `progress`, `blocker`, `reflection`, or `related`, plus concise feedback. You can correct or remove it before confirming the entry. Confirmed interpretations remain analytical annotations: they do not change goal status, create goal events, or become authoritative goal evidence.

To promote a confirmed entry into authoritative goal evidence, explicitly ask Codex to link it:

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

### Decide whether a message is an ordinary capture

Treat an unqualified declarative message about the user's personal experience, feeling, reflection, decision, life status, or an idea they clearly want to preserve as an ordinary capture. Do not capture direct questions, repository/task commands, content-generation requests, or clearly non-recording messages by default. When genuinely ambiguous, continue the conversation instead of silently capturing.

This broad trigger does not remove the confirmation boundary. Never finalize an entry merely because capture was automatic.

### Entry pipeline

Create the draft before interpreting the user's wording:

```bash
python3 .agents/skills/record-life-journal/scripts/journal.py --root . \
  create-draft --text '<verbatim user input>'
```

Use the returned `entry_id` throughout the turn. Use its routing decision, journal context, and bounded `goal_context` instead of scanning the entire journal tree or all goals. When `goal_context.has_context` is false, skip goal interpretation.

Whole-input `diary`/`thought`/`decision` classification, cleaning, theme classification, and continuity checks are always required. The initial draft type is not authoritative. Classify the complete input once, show the selected type in the preview, and never assign different entry types to its segments. The deterministic cleaner is only a starting candidate:

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
  --entry-type thought \
  --clean-text '<cleaned text>' \
  --segments '[{"text":"...","theme":"primary","tags":["cross-cutting"]}]' \
  --uncertainties '[]' --links '[]' --followups '[]' \
  --agent-feedback '{"feedback_text":"...","trigger_mode":"active","evidence":[]}' \
  --goal-interpretations '[{"goal_id":"...","relation":"progress","evidence":"...","interpretation":"...","feedback":"...","confidence":0.9}]'
```

`--entry-type` is required by the agent protocol for user-input previews and accepts `diary`, `thought`, or `decision`. It may correct any non-confirmed user-input draft, but it cannot convert a weekly review or a confirmed entry. Changing a preview to `decision` requires `--decision`; changing it away from `decision` must omit that payload. Segments stay in narrative order. Each requires a primary `theme`; `tags` are optional, deduplicated, and must not repeat the primary theme. `--agent-feedback` is optional, limited to 200 characters, and may cite only confirmed entries; pass no payload to remove it before confirmation. Goal interpretations are optional, use only Active goals, require evidence from this entry, and can be corrected or removed by saving the preview again. User-input entries may have at most one optional follow-up question.

For an explicit or clearly recognizable decision draft, create it with `create-draft --type decision` and pass `--entry-type decision` plus a JSON decision payload through `save-preview --decision`. The payload must include a do-nothing option and the full analysis structure described above. Missing analysis should be filled by Codex and shown for confirmation before saving.

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

Review pending decisions with `decision-review-context` or through `weekly-context`. To revise, make, or reopen one, first run `decision-change-preview`, show the proposed structure, then apply only the user's explicit per-item decisions with `apply-decision-changes`.

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

Exit without semantic work when `has_content` is false. Otherwise use only the returned current entries, goals, historical connections, reflection candidate, and theme evidence. Summarize `diary_entries` as events, feelings, and time-specific reflection; summarize `thought_entries` as ideas, hypotheses, conceptual changes, and open questions. Keep the combined `entries` field only as a compatibility surface. Each Active goal keeps explicit `weekly_evidence` separate from non-authoritative `weekly_interpretations`; summaries must preserve that distinction and must not silently promote interpretations. Create a weekly draft, show the review plus two to five optional questions, and require confirmation. Keep goal and theme mutations as separately confirmed proposals.

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
| `save-preview` | Store the whole-input diary/thought/decision type, cleaned text, segments, uncertainties, links, follow-ups, optional Agent feedback, decision analysis, and optional AI goal interpretations |
| `confirm` | Finalize a preview and export Markdown |
| `search` | Retrieve relevant confirmed records, optionally filtered by type |
| `add-feedback` | Store workflow friction or a new requirement |
| `update-followup` | Mark a follow-up answered, skipped, or deferred |
| `weekly-context` | Build the previous week's evidence package with separate diary and thought lists |
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

### Project_PA thought migration

The historical thought migration reads `D:\Project_PA\data\project_pa.db` (`/mnt/d/Project_PA/data/project_pa.db` in WSL) without modifying it. Its source filter is:

```sql
user_id = 2
AND lower(category) = 'thought'
AND user_confirmed = 1
AND content is nonempty
```

The completed source audit yielded nine real-user inputs. Two similarly labeled rows belonging to `user_id=1` / `testuser` were excluded. Each source row remains one complete `thought`; it was not split into records with different types or bulk-copied directly into SQLite. Source dates and verbatim content were preserved.

Migration used the normal `create-draft` → `save-preview --entry-type thought` → explicit confirmation path. The approved preview SHA-256 was `951ce47e355590220ef9a45b9467a6a468b82ef1785da2e9b51a93eb66a16c86`. The provenance key is `project_pa:entries:<source_id>@<iso_timestamp>`, with content hashes used as a second duplicate check. The reviewed manifest and immutable human-readable preview live at `data/imports/project_pa_thoughts.json` and `data/imports/project_pa_thoughts_preview.md`. The pre-confirmation backup is `data/backups/diary-20260719-091941.sqlite3` with SHA-256 `6bbff2c9d06cb30fe38a3b75e6a31471778938a17d43f59242303e6de5dafee5`. All nine records were confirmed on 2026-07-19; final verification checks entries, Markdown files, FTS rows, source-key uniqueness, and SQLite integrity.

## Storage and repository map

| Path | Role |
| --- | --- |
| `data/diary.sqlite3` | Authoritative structured diary, thought, decision, separate Agent-feedback, theme, goal, goal-interpretation, workflow-feedback, and revision data |
| `data/drafts/` | Temporary draft/preview state; removed after confirmation |
| `data/backups/` | SQLite backups and SHA-256 manifests |
| `journals/originals/YYYY/MM/` | Verbatim input, including draft/confirmed status |
| `journals/cleaned/YYYY/MM/` | Confirmed cleaned diary, thought, and decision Markdown; frontmatter records the type and Agent feedback appears only in its own section |
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
- Each recordable user input is exactly one `diary`, `thought`, or `decision`; segments do not carry record types. `weekly` is generated separately.
- Agent feedback stays non-authoritative and separate from verbatim text, cleaned text, goals, decision facts, and default FTS indexing.
- Verbatim originals are never replaced by cleaned text.
- Confirmed journals are not silently rewritten by theme or goal governance.
- Goals are explicit user commitments, never inferred from older diary text.
- AI goal interpretations are current-entry annotations, not user-authored facts or authoritative goal evidence.
- Theme, tag, and goal mutations require per-item decisions.
- Follow-up questions are optional and never block confirmation.
- Weekly journal confirmation does not automatically apply goal, theme, or Skill changes.
- The application itself makes no external model call and requires no API key.
