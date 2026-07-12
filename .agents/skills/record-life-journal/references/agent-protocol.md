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
