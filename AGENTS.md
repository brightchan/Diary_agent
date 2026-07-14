# Diary Agent working agreement

- Keep the project local-first and standard-library-first.
- Never add an OpenAI API client, API key requirement, or external model call. Semantic work is performed by Codex and its subagents.
- Use `.agents/skills/record-life-journal/SKILL.md` for diary workflows.
- Treat an unqualified declarative message about the user's personal experience, feeling, reflection, decision, or life status as diary capture. Do not capture direct questions, repository/task commands, or clearly non-diary requests by default.
- Preserve verbatim originals. Do not rewrite confirmed journals outside the core confirmation/export path.
- Track `data/diary.sqlite3` and every file under `journals/` in Git. Ignore only SQLite WAL/SHM sidecars and disposable caches.
- Skill changes require a stored proposal, an automatic pre-change Git snapshot, explicit user approval, validation, tests, and a post-change Git snapshot.
- Use `python -m pytest` and the skill-creator `quick_validate.py` before marking a Skill revision applied.
- For repository tests, agents may use the existing conda environment at `/mnt/d/Project_PA/condaenv_host`; invoke pytest as `/mnt/d/Project_PA/condaenv_host/bin/python -m pytest` without modifying or recreating that environment.
