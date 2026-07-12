# Weekly skill improvement

Build a proposal from unprocessed feedback without changing the active Skill.

The proposal JSON must contain:

```json
{
  "feedback_ids": ["uuid"],
  "problem_summary": "string",
  "impact": "string",
  "proposed_diff": "unified diff or precise edit plan",
  "compatibility": "string",
  "tests": ["string"],
  "token_cost_change": "decrease|neutral|increase with reason"
}
```

Run `propose-skill-revision --proposal '<json-or-file>'`. It stores the proposal, marks feedback planned, runs `git add -A`, and commits the complete repository including SQLite and all journals. It records the snapshot commit in the revision audit.

After explicit approval, apply the diff, validate the Skill, run tests, then mark the revision `applied`. Mark it `failed` with a test summary when validation fails. Both outcomes create another Git snapshot.
