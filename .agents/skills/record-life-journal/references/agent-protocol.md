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

## Classifier output

```json
{
  "segments": [
    {"text": "exact or faithful span", "theme": "string", "theme_status": "existing|proposed"}
  ],
  "merge_suggestions": []
}
```

Preserve narrative order. Never apply `merge_suggestions` automatically.

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

## Merged preview

Pass arrays to `save-preview` as JSON strings or files:

```bash
python .agents/skills/record-life-journal/scripts/journal.py --root . save-preview \
  --entry-id '<uuid>' \
  --clean-text '<preview text>' \
  --segments '[{"text":"...","theme":"..."}]' \
  --uncertainties '[]' --links '[]' --followups '[]'
```

Do not include chain-of-thought or full historical records.

## Theme-governance output

Pass review items to `save-theme-review` before asking for decisions:

```json
[
  {
    "action": "deactivate|activate|rename|merge|split|create|reassign_segment",
    "source_theme_id": "uuid or null",
    "target_theme_id": "uuid or null",
    "payload": {},
    "evidence": [{"entry_id": "uuid", "segment_id": "uuid", "reason": "string"}]
  }
]
```

Show each proposal and its evidence. Pass only the user's per-item `approved` or `rejected` decisions to `apply-theme-changes`. A split does not imply historical reclassification.

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
