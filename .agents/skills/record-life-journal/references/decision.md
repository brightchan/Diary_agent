# Decision capture and review

Use full parent-model analysis for every `decision`. Fetch the `decision` context profile when the initial draft did not already load it. Keep facts, assumptions, and Agent judgement separate. Never convert a recommendation into a made decision.

Every preview must contain:

```json
{
  "status": "pending|made",
  "objective": "user objective",
  "options": [
    {
      "name": "option",
      "is_do_nothing": false,
      "facts": [],
      "assumptions": [],
      "reversible_consequences": [],
      "irreversible_consequences": []
    }
  ],
  "opportunity_cost": {"facts": [], "assumptions": [], "judgement": ""},
  "likely_regret": {"one_year": "", "five_years": ""},
  "assumptions": [],
  "smallest_experiment": {
    "action": "",
    "uncertainty_reduced": "",
    "timebox": "",
    "success_signal": ""
  },
  "recommendation": {"option": "", "facts": [], "assumptions": [], "judgement": ""},
  "timeline": {"review_date": "YYYY-MM-DD", "due_date": "YYYY-MM-DD", "notes": ""}
}
```

Include at least two options and a clearly labelled do-nothing/no-action option. Fill omitted analysis as Agent analysis and show it for confirmation. A pending decision remains open; a made decision archives only after confirmation.

Agent feedback may be at most 200 Chinese characters, must remain separate from the full decision structure, and may cite only returned confirmed thought/decision records.

Later updates require `decision-change-preview` and explicit approval through `apply-decision-changes`. Weekly confirmation never marks a decision made.
