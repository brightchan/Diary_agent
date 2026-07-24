---
name: record-life-journal
description: Capture, clean, classify, preview, confirm, search, and summarize local diary, thought, and decision records; run weekly reviews; govern themes and life, long-term, short-term, or weekly goals; and improve the diary workflow. Use for personal experiences, feelings, reflections, ideas, pending or made decisions, spoken-text cleanup, journal recall, goal context, weekly journaling, workflow feedback, or diary Skill revisions.
---

# Record Life Journal

Keep the user's wording and facts authoritative. Use only local files, SQLite, Codex, and Codex subagents; never require an OpenAI API key or external model call.

## Preserve the safety boundary

- Treat an unqualified statement about the user's experience, feeling, reflection, decision, or life status as capture. Do not capture direct questions, repository commands, or clearly non-recording requests.
- Create a draft from the verbatim input before interpreting it. Never alter the original.
- Show one complete preview and require explicit confirmation before final storage. After any correction or supplement, save and show a new complete preview.
- Keep Agent feedback, goal interpretations, decision analysis, and weekly analysis visibly separate from user-authored text.
- Treat SQLite as truth. Never silently rewrite confirmed originals or cleaned Markdown.

## Route before loading detail

Read only the reference required by the current route:

| Route | Required reference | Default depth |
| --- | --- | --- |
| Ordinary diary capture | [capture.md](references/capture.md) | Fast; no history, goals, or feedback |
| Thought capture | [capture.md](references/capture.md), then [thought.md](references/thought.md) | Fast compact feedback |
| Decision capture/review | [capture.md](references/capture.md), then [decision.md](references/decision.md) | Full structured analysis |
| Weekly review | [weekly.md](references/weekly.md) | Deep local context |
| Search/recall | [capture.md](references/capture.md) | Query-bounded |
| Theme/goal governance | [governance.md](references/governance.md) | Approval-gated |
| Workflow feedback or Skill revision | [skill-improvement.md](references/skill-improvement.md) | Proposal-gated |

Do not read every reference. Read [storage-schema.md](references/storage-schema.md) only for schema or migration work.

## Start capture

Run:

```bash
python .agents/skills/record-life-journal/scripts/journal.py --root . create-draft \
  --analysis-mode auto --text '<verbatim input>'
```

Use `--type decision` for an explicit decision. Use `--analysis-mode deep` only when the user asks for historical or goal analysis. `auto` loads compact context only for explicit decisions, strong continuity, or strong goal signals; `none` forbids contextual retrieval.

Classify the whole input exactly once:

- `diary`: lived events, feelings, personal status, or time-specific reflection.
- `thought`: a proposition, hypothesis, conceptual question, model, or reusable insight.
- `decision`: a meaningful pending or made choice between options.

Keep subjects in ordered theme segments and tags, not entry types. The previewed type overrides the draft type.

## Route semantic work efficiently

- For a short clear input, keep cleaning verbatim, classify in the parent, and do not spawn a subagent.
- When `routing_decision.delegate.fast_worker` is true, use at most one project agent named `diary_fast`. It combines cleaning and classification with `gpt-5.6-terra` at low reasoning effort. Pass only the verbatim input, cleaning mode/style, and returned theme candidates. Do not send historical journals.
- Keep decision and weekly judgement in the parent model. Never fan out cleaner, classifier, and continuity workers for ordinary capture.
- If a draft is reclassified or the user requests more depth, run `capture-context --entry-id '<id>' --profile continuity|thought|decision|goals|deep`. Re-run only the affected stage.

## Preview and confirm

Pass the whole-input type through `save-preview --entry-type diary|thought|decision`. A decision preview requires the complete decision payload; a non-decision preview must omit it.

Show the cleaned text, ordered themes/tags, uncertainties, optional links/question, and only the route-specific analysis. Do not confirm in the same step unless the user explicitly confirms the displayed version.

On confirmation, run:

```bash
python .agents/skills/record-life-journal/scripts/journal.py --root . confirm --entry-id '<id>'
```

Confirmation is idempotent. Report both stored Markdown paths.

## Search and token discipline

Run `search --query '<question>'`, adding `--type diary|thought|decision` when appropriate. Use only returned records, cite dates, and label inference. Never restate stored Agent feedback as the user's historical view.

Use deterministic routing, FTS5, theme/entity indexes, and n-gram similarity before semantic work. Stop when extra context adds no new fact or relationship. Do not scan the journal tree, pass full history to a worker, or reload unaffected stages.
