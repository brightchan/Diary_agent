# Fast capture and recall

Use this reference for ordinary capture, shared preview payloads, and search.

## Fast path

1. Create the verbatim draft with `--analysis-mode auto`.
2. Trust `context_state`: empty profiles mean no continuity or goal analysis is needed.
3. Use `theme_candidates` as compact reuse evidence. Propose a new theme only when no candidate fits.
4. Preserve written input verbatim except accidental outer whitespace. For obvious speech artifacts, remove only non-semantic fillers and repair clearly broken repetitions or boundaries.
5. Flag uncertain people, companies, projects, objects, dates, numbers, and referents; never guess.
6. Save and show the complete preview. Wait for explicit confirmation.

For an explicit deep request use `--analysis-mode deep`. After draft creation, fetch only missing context with:

```bash
python .agents/skills/record-life-journal/scripts/journal.py --root . capture-context \
  --entry-id '<uuid>' --profile continuity|thought|decision|goals|deep
```

## Cleaning and classification output

```json
{
  "entry_type": "diary|thought|decision",
  "clean_text": "string",
  "uncertainties": [{"span": "string", "reason": "string", "candidates": ["string"]}],
  "segments": [
    {"text": "exact or faithful span", "theme": "primary theme", "tags": ["cross-cutting theme"]}
  ]
}
```

Keep material meaning changes out of `clean_text`. Preserve narrative order. Give every segment one primary theme; deduplicate tags and omit the primary theme from tags. Exclude inactive themes and resolve merged names to their active canonical target.

## Optional continuity and goals

Create a link only from returned evidence:

```json
{"target_entry_id":"uuid","relation":"continuation|related|changed_view|action_followup","reason":"evidence","score":0.0}
```

Ask at most one optional reflection question. Goal interpretations may use only returned active goals and must remain non-authoritative annotations with `progress|blocker|reflection|related`, current-entry evidence, interpretation, feedback, and confidence. They never create or change goals.

## Save preview

Pass JSON inline or by file:

```bash
python .agents/skills/record-life-journal/scripts/journal.py --root . save-preview \
  --entry-id '<uuid>' --entry-type diary --clean-text '<text>' \
  --segments '[{"text":"...","theme":"...","tags":[]}]' \
  --uncertainties '[]' --links '[]' --followups '[]'
```

For diary, omit Agent feedback unless explicitly requested; requested feedback is `passive`, non-authoritative, and at most 200 Chinese characters.

## Search

Use `search` results only. Retrieval is bounded by serialized size, relevance, and novelty rather than a fixed record count. Returned `agent_feedback` is Agent analysis, never user-authored history.
