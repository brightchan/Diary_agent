# Weekly review

At the configured weekly review time:

1. Run `weekly-context`. Exit without an Agent call when `has_content` is false.
2. Create a weekly draft for the returned period.
3. Keep diary events, feelings, progress, blockers, unfinished threads, and next actions separate from thought hypotheses and conceptual changes.
4. Use returned historical connections only when their cited segments support the pattern. Never promote Agent feedback or weekly interpretations into user beliefs, goal evidence, or decision facts.
5. Include returned goal-adjustment drafts, theme suggestions, and pending-decision review as separate approval-gated items. Fill missing decision analysis but do not mark decisions made.
6. Ask 2-5 optional questions and show the complete weekly preview.
7. Immediately publish the generated preview with `git-publish`. Publish again after confirmation or later corrections. Do not report completion until push succeeds.

Use a historical reflection question only when `reflection_prompt_candidate` is present. Theme and goal changes require their dedicated governance commands and are never applied through weekly confirmation.
