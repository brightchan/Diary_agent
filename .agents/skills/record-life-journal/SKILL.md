---
name: record-life-journal
description: Capture clear personal-life statements by default; clean, classify, tag, connect, review, confirm, search, and summarize diary entries and pending or made decisions; govern themes and confirmed life, multi-year long-term, within-one-year short-term, or weekly goals with local SQLite and Markdown storage. Use for daily or weekly journaling, decision capture and review, standalone personal experiences or reflections, spoken-text cleanup, life-theme classification, goal context, follow-up reflection, recalling prior experiences, workflow feedback, or diary skill improvements.
---

# Record Life Journal

Keep the user's wording and facts authoritative. Use Codex agents only; never request, read, or call an OpenAI API key.

## Default personal-life capture

Treat an unqualified declarative message about the user's own experience, feeling, reflection, decision, or life status as a diary entry even when the user does not say “record this.” Do not default to diary capture for a direct question, repository or task command, request for information or content, or other clearly non-diary message. When the distinction is genuinely unclear, continue the conversation instead of silently capturing it.

The broader trigger does not change the safety boundary: preserve the verbatim message in a draft first, show a preview, and require explicit confirmation before final storage.

## Decision capture and review

When the user's statement is about choosing between meaningful options, route it as a `decision` entry when the user asks to track it as a decision or when the intent is clearly to preserve a pending or made choice. Decisions use the same ordered segments, primary themes, and cross-cutting tags as diary entries.

Every decision preview must contain:

- `status`: `pending` or `made`;
- the user's actual objective;
- options, including doing nothing/no action;
- facts, assumptions, reversible consequences, and irreversible consequences for each option;
- opportunity cost;
- likely regret in one and/or five years;
- assumptions that could be wrong;
- the smallest experiment that would reduce uncertainty; and
- one recommended option.

Keep facts, assumptions, and the agent's judgement visibly separate. If the user did not supply part of this analysis, the agent may draft it from the user's entry and retrieved local evidence, but must label it as agent analysis and ask the user to confirm the completed decision preview. Do not silently turn a recommendation into a made decision. A `made` decision is archived for future reference after confirmation; a `pending` decision remains open.

Pending decisions may include a review date and/or due date. During weekly review, use `decision_review` from `weekly-context` to surface overdue and upcoming decisions, explain the reminder, propose a next action, and fill the same structure so the user can confirm, defer with a new timeline, run the smallest experiment, or leave it pending. Updating a pending decision or changing it to `made` requires `decision-change-preview` followed by explicit approval through `apply-decision-changes`.

## Start every capture safely

1. Run `python .agents/skills/record-life-journal/scripts/journal.py --root . create-draft --text '<verbatim input>'` before interpreting the entry.
2. Treat the returned `entry_id` as the only identifier for the turn.
3. Use the returned routing decision and retrieved context. Do not scan the full journal tree.
4. Use the returned `cleaning_style` as a compact preservation guide. A style profile may prevent unnecessary edits; it never authorizes embellishment, normalization, or rewriting.
5. Use the returned `goal_context` after cleaning and classification. When it contains relevant Active goals, prepare compact goal interpretations before merging the preview; when it is empty, skip that semantic stage.
6. Read [agent-protocol.md](references/agent-protocol.md) before producing or merging an analysis payload.

For a decision, use `create-draft --type decision`, and pass the structured decision analysis through `save-preview --decision`. The normal entry confirmation remains the only confirmation boundary for the initial decision record.

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

- First decide whether the input is obviously speech-like. If it is not, default to `clean_text` matching the verbatim input; apart from trimming accidental outer whitespace, make no change merely to make the prose smoother or more standard.
- Never beautify, formalize, replace words with synonyms, regularize intentional punctuation, or rewrite sentence structure. Do not erase the user's characteristic brevity, repetition, code-switching, colloquial wording, or narrative rhythm.
- When obvious speech artifacts exist, remove only non-semantic fillers such as `嗯`, `呃`, and repeated hesitation, then repair only clearly broken punctuation, repeated fragments, or sentence boundaries.
- Make the smallest edit that resolves the specific artifact. The absence of standard written style is not itself an artifact.
- Preserve facts, negation, emotional intensity, uncertainty, voice, and chronology.
- Flag uncertain people, terms, dates, numbers, and referents. Never silently guess them.
- Use `cleaning_style` only when it is supported by confirmed original entries. When no profile exists or evidence is insufficient, fall back to verbatim preservation instead of inventing preferences.

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

Show one concise preview containing cleaned full text, ordered theme segments, proposed new themes, uncertainties, relevant prior entries with reasons, AI goal interpretations when present, the full decision analysis when this is a decision, and at most one optional reflection question. Keep interpretations and decision analysis separate from the user's narrative. Make clear which decision fields are user-supplied facts, agent-labelled assumptions, and agent judgement.

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
2. Exit without an agent call when `has_content` is false. Pending decisions alone make `has_content` true so a scheduled decision reminder is not lost.
3. When content exists, create a weekly draft covering the returned period.
4. Use `historical_connections` when present to summarize evidence-backed patterns, changes, repeated blockers, and unfinished threads across weeks. Never imply a connection that the returned evidence does not support.
5. Summarize facts, feelings/insights, theme and tag progress, goal progress and blockers, unfinished threads, and next-week actions. Treat `weekly_interpretations` as non-authoritative inferred evidence, keep it distinct from explicit `weekly_evidence`, and never promote it to a goal link or mutate a goal silently.
6. Ask an optional historical reflection question only when `reflection_prompt_candidate` is present and its cited historical segment supports the question.
7. Include goal-adjustment drafts and theme-governance suggestions as separate review items. Never apply them through weekly-journal confirmation.
8. Include `decision_review` suggestions for pending decisions. For overdue or upcoming items, fill missing analysis fields, recommend one option, and distinguish facts, assumptions, and judgement. Never mark a decision made through weekly-journal confirmation; use an explicit decision change proposal.
9. Add 2-5 optional questions and wait for confirmation before final storage.
10. Immediately after generating and saving the weekly review preview, run `git-publish` with a period-specific message. Publish again after confirmation or any later correction changes repository state. Do not report the review generation or confirmation complete until the push succeeds.

## Govern themes and goals

Read [agent-protocol.md](references/agent-protocol.md) before preparing change payloads.

- Run `theme-review-context` for Active, Inactive, and Merged themes plus compact usage evidence. Save suggestions with `save-theme-review`; apply only explicit per-item decisions through `apply-theme-changes`.
- Support `create`, `activate`, `deactivate`, `rename`, `merge`, `split`, explicit primary-theme `reassign_segment`, and explicit `add_segment_tag` or `remove_segment_tag`. Split creates Active replacements and deactivates the source; it never rewrites historical segments unless a separate proposal is approved.
- Keep Inactive theme text searchable through entry full text, but exclude its tag from default theme-driven retrieval. Keep Merged history and resolve it to the canonical Active theme.
- Save goal proposals with `goal-change-preview`; apply only explicit per-item decisions through `apply-goal-changes`. Never infer an old diary statement into a user goal.
- Classify `life` as an open-ended life direction, `long_term` as a goal spanning multiple years, `short_term` as a goal intended to finish within one year, and `weekly` as a one-week focus. Use `life -> long_term -> short_term -> weekly` as the breadth order while allowing a child to omit intermediate parents.
- Use `goal-context` for goal review. Use `conversation-context` to retrieve only relevant Active goals, recent events, and a small evidence set for a current question.
- Automatic entry goal interpretations are confirmed analytical annotations only. Explicit `link_entry` proposals remain the path for promoting diary evidence into authoritative goal evidence.
- Decision status and analysis are authoritative only after decision preview confirmation. Use `decision-change-preview` and `apply-decision-changes` for later updates, including `make` and `reopen`; these updates may refresh the decision section of confirmed Markdown but never alter the original.
- Treat SQLite as truth. Regenerate `memory/goals.md` only after confirmed goal changes. Never modify originals or silently rewrite confirmed cleaned Markdown when theme or goal state changes.

## Feedback and weekly skill improvement

### Weekly cleaning-style calibration

At Monday 02:00 Asia/Singapore, before reviewing workflow feedback:

1. Run `cleaning-style-context`. It returns only bounded, newly confirmed non-weekly originals, their cleaning comparisons, and the current compact profile.
2. Exit this stage without an agent call when `has_new_samples` is false. When `ready_for_review` is false, keep accumulating originals and do not infer a profile from insufficient evidence.
3. When ready, infer only stable, observable habits from the verbatim originals: sentence length, punctuation, Chinese-English code-switching, degree of colloquialism, recurring wording, repetition, and narrative rhythm. Use clean/original differences only to detect over-cleaning.
4. Keep the profile compact and evidence-backed. Record a `summary`, `preserve` items, `avoid` items, and observations shaped as `{trait, evidence}`. Do not store speculative personality claims or treat a one-off phrase as a lasting preference.
5. Run `save-cleaning-style` with the profile and every source entry id used. This updates `memory/cleaning-style.md` and the SQLite audit record without rewriting any original or confirmed cleaned journal.
6. Future captures receive the latest profile through `create-draft`; it remains subordinate to the current verbatim input and the preview-confirm boundary.

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
