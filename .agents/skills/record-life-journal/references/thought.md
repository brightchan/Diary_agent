# Thought capture

Use this reference only after the shared fast capture reference classifies the whole input as `thought`.

- Preserve the original thought before responding.
- By default, add one separate `active` Agent feedback paragraph of at most 120 Chinese characters. Do not retrieve history or browse for evidence. State a useful strength, limit, counterpoint, or applicability boundary without forcing unsupported structure.
- When the user explicitly asks to discuss, compare, synthesize, or find related history/evidence, fetch `capture-context --profile thought` or `deep` and expand the discussion. Cite confirmed local dates and distinguish evidence from inference.
- Keep feedback non-authoritative and outside `clean_text`:

```json
{
  "feedback_text": "up to 120 Chinese characters by default",
  "trigger_mode": "active",
  "evidence": []
}
```

The user may keep the original, provide replacement text, request a synthesis, skip discussion, or decline storage. Put a synthesis into `clean_text` only after the user selects it and sees a new preview. `直接入库` skips discussion but never skips preview and explicit confirmation.
