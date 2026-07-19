# Agent protocol

Use this compact contract between cleaner, classifier, continuity, and orchestrator roles.

## Whole-input entry-type output

Classify the complete user input once before merging the preview:

```json
{
  "entry_type": "diary|thought|decision",
  "reason": "short evidence-based reason tied to the input's dominant purpose"
}
```

Use `diary` for input primarily anchored to lived events, feelings, personal status, or time-specific reflection. Use `thought` for input primarily preserving a proposition, hypothesis, conceptual question, model, interpretation, or reusable insight. Use `decision` for a meaningful pending or made choice and include the full Decision output below. Honor an explicit user type. Never classify separate segments of one input into different record types; use themes and tags for physics, biology, life, philosophy, and other subjects. Keep `weekly` for system-generated review output.

## Cleaner output

```json
{
  "clean_text": "string",
  "uncertainties": [
    {"span": "string", "reason": "string", "candidates": ["string"]}
  ],
  "material_changes": []
}
```

`material_changes` must stay empty. If an edit could change meaning, move it to `uncertainties`.

Before cleaning, inspect the routing signal and compact `cleaning_style` returned by `create-draft`:

- When `cleaning_mode` is `preserve_verbatim`, return the verbatim input as `clean_text` apart from accidental outer whitespace.
- A lack of polished written punctuation or formal phrasing is not a reason to edit. Do not beautify, formalize, synonym-swap, or restructure the user's prose.
- When minimal cleaning is justified, change only the specific obvious speech artifact and preserve characteristic repetition, code-switching, wording, punctuation, and rhythm.
- Treat the persisted style profile as evidence about what to preserve, not a template to force onto new input. If it conflicts with the current original, the current original wins.

## Classifier output

```json
{
  "segments": [
    {"text": "exact or faithful span", "theme": "primary theme", "tags": ["optional cross-cutting theme"], "theme_status": "existing|proposed"}
  ],
  "merge_suggestions": []
}
```

Preserve narrative order. `theme` is required. `tags` is optional, deduplicated, and must not repeat the primary theme. Legacy `{text, theme}` payloads remain valid. Never apply `merge_suggestions` automatically.

## Continuity output

```json
{
  "links": [
    {
      "target_entry_id": "uuid",
      "relation": "continuation|related|changed_view|action_followup",
      "reason": "short evidence-based reason",
      "score": 0.0
    }
  ],
  "followups": [
    {"question": "string", "status": "pending"}
  ]
}
```

User-input output may contain at most one follow-up. Weekly output may contain 2-5.

## Agent-feedback output

Keep Agent feedback separate from user-authored text and all authoritative facts:

```json
{
  "agent_feedback": {
    "feedback_text": "up to 200 Chinese characters including punctuation",
    "trigger_mode": "active|passive",
    "evidence": [
      {"entry_id": "confirmed uuid", "date": "YYYY-MM-DD", "type": "diary|thought|decision|weekly", "reason": "why it is relevant"}
    ],
    "authoritative": false
  }
}
```

- Omit or pass `null` when no feedback should be stored. For `diary`, default to no feedback and generate it only on an explicit user request with `trigger_mode: passive`.
- For `thought`, default to active feedback of 100-200 Chinese characters. When supported, cover both the strongest supporting case and a counterargument, then the idea's strengths, limits, applicability boundary, and closest evidence-backed connection. A missing counterargument or connection is a result, not a reason to invent one.
- For `decision`, default to active feedback of at most 200 Chinese characters. Use bounded confirmed `decision` and `thought` retrieval, cite dates, present supporting reasons and risks, and give conditional advice. Do not replace or duplicate the full Decision output.
- Evidence must refer to confirmed entries returned by local retrieval. Separate evidence from inference and never cite the current unconfirmed entry as its own evidence.
- Never merge `agent_feedback` into `clean_text`, goal evidence, decision facts, or FTS user-text indexing. The user may correct or remove it in the normal preview.

## Goal-interpretation output

Use only the locally filtered Active goals returned in `goal_context`. If it is empty, return no goal interpretations and skip semantic goal analysis.

```json
{
  "goal_interpretations": [
    {
      "goal_id": "active goal uuid",
      "goal_title": "display snapshot",
      "relation": "progress|blocker|reflection|related",
      "evidence": "exact or faithful evidence from the current entry",
      "interpretation": "concise evidence-based interpretation",
      "feedback": "concise goal-related feedback",
      "confidence": 0.0
    }
  ]
}
```

These are AI-generated analytical annotations, not user-authored facts, `goal_events`, or authoritative `goal_entry_links`. They must not create or mutate goals. The user may correct or remove them in the normal diary preview.

## Decision output

For a decision entry or pending-decision weekly review, use this payload shape:

```json
{
  "status": "pending|made",
  "objective": "the user's actual objective",
  "options": [
    {
      "name": "option name",
      "is_do_nothing": false,
      "facts": ["..."],
      "assumptions": ["..."],
      "reversible_consequences": ["..."],
      "irreversible_consequences": ["..."]
    }
  ],
  "opportunity_cost": {"facts": ["..."], "assumptions": ["..."], "judgement": "..."},
  "likely_regret": {"one_year": "...", "five_years": "..."},
  "assumptions": ["assumptions that could be wrong"],
  "smallest_experiment": {"action": "...", "uncertainty_reduced": "...", "timebox": "...", "success_signal": "..."},
  "recommendation": {"option": "...", "facts": ["..."], "assumptions": ["..."], "judgement": "..."},
  "timeline": {"review_date": "YYYY-MM-DD", "due_date": "YYYY-MM-DD", "notes": "..."}
}
```

The options array must include a clearly labelled do-nothing/no-action option. Fill omitted analysis from the current entry and bounded retrieved evidence, but label it as agent analysis and show it for confirmation. Keep facts, assumptions, and judgement distinct; recommendation is judgement, not fact. A pending-to-made transition is a separate explicit decision-change proposal, not an implicit consequence of weekly-journal confirmation.

## Merged preview

Pass arrays to `save-preview` as JSON strings or files:

```bash
python .agents/skills/record-life-journal/scripts/journal.py --root . save-preview \
  --entry-id '<uuid>' \
  --entry-type 'diary|thought|decision' \
  --clean-text '<preview text>' \
  --segments '[{"text":"...","theme":"...","tags":["..."]}]' \
  --uncertainties '[]' --links '[]' --followups '[]' \
  --agent-feedback '{"feedback_text":"...","trigger_mode":"active","evidence":[]}' \
  --goal-interpretations '[{"goal_id":"...","relation":"progress","evidence":"...","interpretation":"...","feedback":"...","confidence":0.9}]'
```

Do not include chain-of-thought or full historical records. `save-preview` normalizes Agent-feedback evidence dates and types from confirmed entries; confirmation persists the normalized value separately.

## Theme-governance output

Pass review items to `save-theme-review` before asking for decisions:

```json
[
  {
    "action": "deactivate|activate|rename|merge|split|create|reassign_segment|add_segment_tag|remove_segment_tag",
    "source_theme_id": "uuid or null",
    "target_theme_id": "uuid or null",
    "payload": {},
    "evidence": [{"entry_id": "uuid", "segment_id": "uuid", "reason": "string"}]
  }
]
```

Show each proposal and its evidence. Pass only the user's per-item `approved` or `rejected` decisions to `apply-theme-changes`. A split does not imply historical reclassification. `reassign_segment` changes the primary theme. Tag additions and removals require their own explicit proposals and never rewrite confirmed Markdown.

## Goal-change output

Pass proposed changes to `goal-change-preview`:

```json
[
  {
    "action": "create|update|complete|pause|abandon|activate|link_entry",
    "goal_id": "uuid when applicable",
    "payload": {},
    "evidence": [{"entry_id": "confirmed uuid", "reason": "string"}]
  }
]
```

`create` requires `scope` and `title`. Use `life` for an open-ended life direction, `long_term` for a goal spanning multiple years, `short_term` for a goal intended to finish within one year, and `weekly` for a one-week focus. Use `ref` and `parent_ref` for a newly proposed hierarchy in one preview; parents must be broader in the `life -> long_term -> short_term -> weekly` order, though intermediate levels may be omitted. `link_entry` requires a confirmed entry plus `progress`, `blocker`, `reflection`, or `related`. Do not convert inference into a goal. Apply only explicit per-item decisions.
