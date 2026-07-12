---
name: record-life-journal
description: Capture, clean, classify, connect, review, confirm, search, and summarize personal diary entries with local SQLite and Markdown storage. Use for daily or weekly journaling, spoken-text cleanup, life-theme classification, follow-up reflection, recalling prior experiences, recording workflow feedback, or proposing improvements to this diary skill.
---

# Record Life Journal

Keep the user's wording and facts authoritative. Use Codex agents only; never request, read, or call an OpenAI API key.

## Start every capture safely

1. Run `python .agents/skills/record-life-journal/scripts/journal.py --root . create-draft --text '<verbatim input>'` before interpreting the entry.
2. Treat the returned `entry_id` as the only identifier for the turn.
3. Use the returned routing decision and retrieved context. Do not scan the full journal tree.
4. Read [agent-protocol.md](references/agent-protocol.md) before producing or merging an analysis payload.

## Route semantic work

Always complete cleaning, classification, and continuity checks. Delegate only where local signals or your own uncertainty justify it.

- Delegate cleaning when speech artifacts, broken sentence boundaries, uncertain terms, or risky corrections exist.
- Delegate classification when multiple themes, new themes, or overlapping historical themes require independent judgment.
- Delegate continuity when prior entries contain a likely continuation, unfinished action, or changed belief.
- For a short, clear entry, perform stages in the orchestrator instead of creating ceremonial subagents.
- For a complex entry or weekly review, run independent cleaner, classifier, and continuity agents in parallel when subagents are available. Pass only task-specific input and retrieved evidence.
- Prefer a lightweight model for cleaner/classifier when the surface exposes model routing. Otherwise inherit the current Codex model and minimize context.

Do not reveal hidden reasoning. Record only routing decisions, evidence links, and compact results.

## Clean conservatively

- Remove non-semantic fillers such as `嗯`, `呃`, and repeated hesitation.
- Repair punctuation, repeated fragments, and obvious sentence boundaries.
- Preserve facts, negation, emotional intensity, uncertainty, voice, and chronology.
- Flag uncertain people, terms, dates, numbers, and referents. Never silently guess them.

Use the deterministic local cleaner only as a starting candidate:

```bash
python .agents/skills/record-life-journal/scripts/journal.py --root . local-clean --text '<text>'
```

## Classify and connect

- Preserve one complete narrative and represent multiple ideas as ordered segments.
- Reuse an existing theme when evidence supports it. Mark a proposed new theme in the preview.
- Never merge themes without explicit confirmation.
- Link an older entry only when the relationship is supported by its text. Separate evidence from inference.
- Ask at most one ordinary-diary reflection question, only for a meaningful unfinished or continuing thread.
- Let the user answer, skip, or defer a question. A skipped question must not block confirmation.

## Preview before confirmation

Show one concise preview containing cleaned full text, ordered theme segments, proposed new themes, uncertainties, relevant prior entries with reasons, and at most one optional reflection question.

After corrections, call `save-preview` with schema-valid JSON. Do not confirm in the same step unless the user explicitly confirms the displayed version.

On explicit confirmation:

```bash
python .agents/skills/record-life-journal/scripts/journal.py --root . confirm --entry-id '<id>'
```

Confirmation is idempotent. Report the stored original and cleaned Markdown paths.

## Search and recall

Run `search --query '<question>'`. Retrieval has no fixed item-count limit; it stops by relevance, novelty, and token budget. Use returned records only, cite dates, and label inference.

## Weekly journal automation

At Monday 01:00 Asia/Singapore:

1. Run `weekly-context`.
2. Exit without an agent call when `has_content` is false.
3. When content exists, create a weekly draft covering the returned period.
4. Summarize facts, feelings/insights, theme progress, unfinished threads, and next-week actions.
5. Add 2-5 optional questions and wait for confirmation before final storage.

## Feedback and weekly skill improvement

- When the user reports friction, a new need, a bad question, or a workflow preference, immediately run `add-feedback`.
- At Monday 02:00 Asia/Singapore, run `feedback-review-context`; exit without an agent call when `has_feedback` is false.
- For feedback, read [skill-improvement.md](references/skill-improvement.md), produce a reviewable proposal, and run `propose-skill-revision`.
- Proposal creation automatically commits the complete repository state, including `data/diary.sqlite3` and every diary Markdown file.
- Never modify the active Skill from a proposal alone. Apply only after explicit user approval, validate and test, then run `mark-skill-revision --status applied`.

## Token discipline

- Use local routing, FTS5, entity/theme indexes, and CPU n-gram similarity before semantic agents.
- Do not impose a fixed count of historical fragments.
- Stop adding context when additional records add no new fact, relationship, theme, or unfinished thread.
- Pass each subagent only the fields needed for its role.
- Re-run only stages affected by a correction.
- Prefer confirmed cleaned text and cached theme summaries for weekly work; consult originals only to resolve evidence gaps.
