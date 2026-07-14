---
name: record-life-journal
description: Capture clear personal-life statements by default; clean, classify, tag, connect, review, confirm, search, and summarize diary entries; govern themes and confirmed life, short-term, or weekly goals with local SQLite and Markdown storage. Use for daily or weekly journaling, standalone personal experiences or reflections, spoken-text cleanup, life-theme classification, goal context, follow-up reflection, recalling prior experiences, workflow feedback, or diary skill improvements.
---

# Record Life Journal

Keep the user's wording and facts authoritative. Use Codex agents only; never request, read, or call an OpenAI API key.

## Default personal-life capture

Treat an unqualified declarative message about the user's own experience, feeling, reflection, decision, or life status as a diary entry even when the user does not say “record this.” Do not default to diary capture for a direct question, repository or task command, request for information or content, or other clearly non-diary message. When the distinction is genuinely unclear, continue the conversation instead of silently capturing it.

The broader trigger does not change the safety boundary: preserve the verbatim message in a draft first, show a preview, and require explicit confirmation before final storage.

## Start every capture safely

1. Run `python .agents/skills/record-life-journal/scripts/journal.py --root . create-draft --text '<verbatim input>'` before interpreting the entry.
2. Treat the returned `entry_id` as the only identifier for the turn.
3. Use the returned routing decision and retrieved context. Do not scan the full journal tree.
4. Use the returned `goal_context` after cleaning and classification. When it contains relevant Active goals, prepare compact goal interpretations before merging the preview; when it is empty, skip that semantic stage.
5. Read [agent-protocol.md](references/agent-protocol.md) before producing or merging an analysis payload.

## Route semantic work

Always complete cleaning, classification, and continuity checks. Delegate only where local signals or your own uncertainty justify it.

- Delegate cleaning when speech artifacts, broken sentence boundaries, uncertain terms, or risky corrections exist.
- Delegate classification when multiple themes, new themes, or overlapping historical themes require independent judgment.
- Delegate continuity when prior entries contain a likely continuation, unfinished action, or changed belief.
- Delegate goal interpretation when deterministic local filtering returns one or more relevant Active goals.
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

- Preserve one complete narrative and represent multiple ideas as ordered segments. Give each segment one primary `theme` and optional cross-cutting `tags`; deduplicate tags and omit the primary theme from `tags`.
- Reuse an Active theme when evidence supports it. Exclude Inactive and Merged themes from new classification candidates; resolve a Merged name to its Active canonical target.
- Mark a proposed new theme in the preview.
- Never merge themes without explicit confirmation.
- Link an older entry only when the relationship is supported by its text. Separate evidence from inference.
- For each locally relevant Active goal, optionally classify current-entry evidence as `progress`, `blocker`, `reflection`, or `related`. Keep the evidence faithful to the current entry, label the result as AI interpretation, and never create, update, link, or change a goal from this stage.
- Ask at most one ordinary-diary reflection question, only for a meaningful unfinished or continuing thread.
- Let the user answer, skip, or defer a question. A skipped question must not block confirmation.

## Preview before confirmation

Show one concise preview containing cleaned full text, ordered theme segments, proposed new themes, uncertainties, relevant prior entries with reasons, AI goal interpretations when present, and at most one optional reflection question. Keep interpretations separate from the user's narrative and make clear that they are evidence-based AI analysis, not user-authored facts or authoritative goal records.

After corrections or removal of any goal interpretation, call `save-preview` with schema-valid JSON. The normal entry preview is the only confirmation boundary; do not add a second per-goal confirmation step. Do not confirm in the same step unless the user explicitly confirms the displayed version.

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
4. Use `historical_connections` when present to summarize evidence-backed patterns, changes, repeated blockers, and unfinished threads across weeks. Never imply a connection that the returned evidence does not support.
5. Summarize facts, feelings/insights, theme and tag progress, goal progress and blockers, unfinished threads, and next-week actions. Treat `weekly_interpretations` as non-authoritative inferred evidence, keep it distinct from explicit `weekly_evidence`, and never promote it to a goal link or mutate a goal silently.
6. Ask an optional historical reflection question only when `reflection_prompt_candidate` is present and its cited historical segment supports the question.
7. Include goal-adjustment drafts and theme-governance suggestions as separate review items. Never apply them through weekly-journal confirmation.
8. Add 2-5 optional questions and wait for confirmation before final storage.
9. Immediately after generating and saving the weekly review preview, run `git-publish` with a period-specific message. Publish again after confirmation or any later correction changes repository state. Do not report the review generation or confirmation complete until the push succeeds.

## Govern themes and goals

Read [agent-protocol.md](references/agent-protocol.md) before preparing change payloads.

- Run `theme-review-context` for Active, Inactive, and Merged themes plus compact usage evidence. Save suggestions with `save-theme-review`; apply only explicit per-item decisions through `apply-theme-changes`.
- Support `create`, `activate`, `deactivate`, `rename`, `merge`, `split`, explicit primary-theme `reassign_segment`, and explicit `add_segment_tag` or `remove_segment_tag`. Split creates Active replacements and deactivates the source; it never rewrites historical segments unless a separate proposal is approved.
- Keep Inactive theme text searchable through entry full text, but exclude its tag from default theme-driven retrieval. Keep Merged history and resolve it to the canonical Active theme.
- Save goal proposals with `goal-change-preview`; apply only explicit per-item decisions through `apply-goal-changes`. Never infer an old diary statement into a user goal.
- Use `goal-context` for goal review. Use `conversation-context` to retrieve only relevant Active goals, recent events, and a small evidence set for a current question.
- Automatic entry goal interpretations are confirmed analytical annotations only. Explicit `link_entry` proposals remain the path for promoting diary evidence into authoritative goal evidence.
- Treat SQLite as truth. Regenerate `memory/goals.md` only after confirmed goal changes. Never modify originals or silently rewrite confirmed cleaned Markdown when theme or goal state changes.

## Feedback and weekly skill improvement

- When the user reports friction, a new need, a bad question, or a workflow preference, immediately run `add-feedback`.
- At Monday 02:00 Asia/Singapore, run `feedback-review-context`; exit without an agent call when `has_feedback` is false.
- For feedback, read [skill-improvement.md](references/skill-improvement.md), produce a reviewable proposal, and run `propose-skill-revision`.
- Proposal creation automatically commits and pushes the complete repository state, including `data/diary.sqlite3` and every diary Markdown file.
- Never modify the active Skill from a proposal alone. Apply only after explicit user approval, validate and test, then run `mark-skill-revision --status applied`.
- A terminal revision result commits and pushes the implementation plus audit metadata. If a push fails after the local commits succeed, preserve them and retry with `git-publish`; do not report the revision complete until the push succeeds.

## Token discipline

- Use local routing, FTS5, entity/theme indexes, and CPU n-gram similarity before semantic agents.
- Do not impose a fixed count of historical fragments.
- Stop adding context when additional records add no new fact, relationship, theme, or unfinished thread.
- Pass each subagent only the fields needed for its role.
- Re-run only stages affected by a correction.
- Prefer confirmed cleaned text and cached theme summaries for weekly work; consult originals only to resolve evidence gaps.
