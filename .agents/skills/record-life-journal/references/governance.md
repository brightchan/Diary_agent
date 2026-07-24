# Theme, goal, and style governance

## Themes

Run `theme-review-context`, save proposals with `save-theme-review`, and apply only explicit per-item decisions through `apply-theme-changes`. Support create, activate, deactivate, rename, merge, split, primary-theme reassignment, and tag addition/removal. A split never rewrites historical segments without a separate approved proposal.

## Goals

Use `goal-context` for review and `conversation-context` for bounded current-question context. Save changes with `goal-change-preview`; apply only explicit per-item decisions through `apply-goal-changes`.

Use `life -> long_term -> short_term -> weekly` as breadth order. Life is open-ended, long-term spans multiple years, short-term finishes within one year, and weekly covers one week. Never infer an old diary statement into a confirmed goal. Promote entry evidence into authoritative goal evidence only through an explicit `link_entry` proposal.

Regenerate `memory/goals.md` only after applied goal changes. Theme and goal state changes never alter originals or silently rewrite confirmed cleaned Markdown.

## Cleaning-style calibration

At the configured weekly calibration time, run `cleaning-style-context`. Exit without an Agent call when there are no new samples; accumulate evidence when `ready_for_review` is false. Infer only stable observable writing habits, save a compact profile with every source entry ID, and never rewrite earlier journals. The current verbatim input always overrides the profile.
