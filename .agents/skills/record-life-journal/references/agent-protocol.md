# Agent protocol

Use this compact contract between cleaner, classifier, continuity, and orchestrator roles.

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

Ordinary diary output may contain at most one follow-up. Weekly output may contain 2-5.

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

## Merged preview

Pass arrays to `save-preview` as JSON strings or files:

```bash
python .agents/skills/record-life-journal/scripts/journal.py --root . save-preview \
  --entry-id '<uuid>' \
  --clean-text '<preview text>' \
  --segments '[{"text":"...","theme":"...","tags":["..."]}]' \
  --uncertainties '[]' --links '[]' --followups '[]' \
  --goal-interpretations '[{"goal_id":"...","relation":"progress","evidence":"...","interpretation":"...","feedback":"...","confidence":0.9}]'
```

Do not include chain-of-thought or full historical records.

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

`create` requires `scope` and `title`. Use `ref` and `parent_ref` for a newly proposed hierarchy in one preview. `link_entry` requires a confirmed entry plus `progress`, `blocker`, `reflection`, or `related`. Do not convert inference into a goal. Apply only explicit per-item decisions.
