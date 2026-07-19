from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import sqlite3
import subprocess
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Singapore")
FILLER_RE = re.compile(r"(?:(?<=^)|(?<=[，。！？；、\s]))(?:嗯+|呃+|额+|哦+|唔+|那个)(?=[，。！？；、\s]|$)")
MULTI_TOPIC_RE = re.compile(r"(?:另外|还有|说到|关于|另一方面|第一|第二|最后|与此同时)")
CONTINUITY_RE = re.compile(r"(?:下周|以后|继续|打算|计划|下一步|还没|尚未|要做|跟进|进展)")
UNCERTAINTY_RE = re.compile(r"(?:可能叫|好像叫|不知道是不是|听起来像|记不清|某个人|某个项目|[?？]{2,})")

GOAL_SCOPES = ("life", "long_term", "short_term", "weekly")
GOAL_SCOPE_RANK = {scope: rank for rank, scope in enumerate(GOAL_SCOPES)}
GOAL_SCOPE_LABELS = {
    "life": "Life",
    "long_term": "Long-term",
    "short_term": "Short-term",
    "weekly": "Weekly",
}

DECISION_STATUSES = ("pending", "made")
ORDINARY_ENTRY_TYPES = ("diary", "thought")
USER_ENTRY_TYPES = (*ORDINARY_ENTRY_TYPES, "decision")
SEARCH_ENTRY_TYPES = ("diary", "thought", "decision", "weekly")
DECISION_STRUCTURE = (
    "objective",
    "options",
    "opportunity_cost",
    "likely_regret",
    "assumptions",
    "smallest_experiment",
    "recommendation",
)


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    entry_type TEXT NOT NULL CHECK(entry_type IN ('diary','weekly','thought','decision')),
    status TEXT NOT NULL CHECK(status IN ('draft','preview','confirmed','cancelled')),
    raw_text TEXT NOT NULL,
    clean_text TEXT,
    entry_date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'codex',
    preview_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmed_at TEXT
);

CREATE TABLE IF NOT EXISTS themes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    merged_into TEXT REFERENCES themes(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS theme_change_proposals (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL CHECK(action IN ('create','activate','deactivate','rename','merge','split','reassign_segment','add_segment_tag','remove_segment_tag')),
    source_theme_id TEXT REFERENCES themes(id),
    target_theme_id TEXT REFERENCES themes(id),
    payload_json TEXT NOT NULL DEFAULT '{}',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','approved','rejected','applied')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    applied_at TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    text TEXT NOT NULL,
    theme_id TEXT REFERENCES themes(id),
    theme_name TEXT NOT NULL,
    UNIQUE(entry_id, position)
);

CREATE TABLE IF NOT EXISTS segment_tags (
    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    theme_id TEXT NOT NULL REFERENCES themes(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY(segment_id, theme_id)
);

CREATE TABLE IF NOT EXISTS entry_links (
    id TEXT PRIMARY KEY,
    source_entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    target_entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(source_entry_id, target_entry_id, relation)
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL DEFAULT 'term',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS followups (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    theme_id TEXT REFERENCES themes(id),
    question TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','answered','skipped','deferred')),
    answer TEXT,
    revisit_after TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK(scope IN ('life','long_term','short_term','weekly')),
    parent_goal_id TEXT REFERENCES goals(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','paused','abandoned')),
    priority INTEGER NOT NULL DEFAULT 0,
    start_date TEXT,
    target_date TEXT,
    success_criteria TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goal_events (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(id),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goal_entry_links (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(id),
    entry_id TEXT NOT NULL REFERENCES entries(id),
    relation TEXT NOT NULL CHECK(relation IN ('progress','blocker','reflection','related')),
    evidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(goal_id, entry_id, relation, evidence)
);

CREATE TABLE IF NOT EXISTS entry_goal_interpretations (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    goal_id TEXT NOT NULL REFERENCES goals(id),
    goal_title TEXT NOT NULL,
    relation TEXT NOT NULL CHECK(relation IN ('progress','blocker','reflection','related')),
    evidence TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    feedback TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL,
    UNIQUE(entry_id, goal_id, relation, evidence)
);

CREATE TABLE IF NOT EXISTS goal_change_proposals (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL CHECK(action IN ('create','update','complete','pause','abandon','activate','link_entry')),
    goal_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','approved','rejected','applied')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    applied_at TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL UNIQUE REFERENCES entries(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('pending','made')),
    objective TEXT NOT NULL,
    options_json TEXT NOT NULL,
    opportunity_cost_json TEXT NOT NULL,
    likely_regret_json TEXT NOT NULL,
    assumptions_json TEXT NOT NULL,
    smallest_experiment_json TEXT NOT NULL,
    recommendation_json TEXT NOT NULL,
    review_date TEXT,
    due_date TEXT,
    timeline_notes TEXT NOT NULL DEFAULT '',
    made_at TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_change_proposals (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK(action IN ('update','make','reopen')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','approved','rejected','applied')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    applied_at TEXT
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'inconvenience',
    status TEXT NOT NULL DEFAULT 'new',
    source_entry_id TEXT REFERENCES entries(id),
    created_at TEXT NOT NULL,
    revision_id TEXT
);

CREATE TABLE IF NOT EXISTS skill_revisions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('proposed','approved','applied','rejected','failed')),
    proposal_json TEXT NOT NULL,
    git_before_commit TEXT,
    git_after_commit TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cleaning_style_profiles (
    id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    source_entry_ids_json TEXT NOT NULL DEFAULT '[]',
    sample_start TEXT NOT NULL,
    sample_end TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    entry_id TEXT REFERENCES entries(id),
    routing_json TEXT NOT NULL,
    context_chars INTEGER NOT NULL DEFAULT 0,
    output_chars INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    entry_id UNINDEXED,
    clean_text,
    themes,
    tokenize='unicode61'
);

CREATE INDEX IF NOT EXISTS idx_themes_status ON themes(status);
CREATE INDEX IF NOT EXISTS idx_segment_tags_theme ON segment_tags(theme_id, segment_id);
CREATE INDEX IF NOT EXISTS idx_theme_changes_status ON theme_change_proposals(status, created_at);
CREATE INDEX IF NOT EXISTS idx_goals_status_scope ON goals(status, scope, priority);
CREATE INDEX IF NOT EXISTS idx_goal_events_goal_created ON goal_events(goal_id, created_at);
CREATE INDEX IF NOT EXISTS idx_goal_links_goal_created ON goal_entry_links(goal_id, created_at);
CREATE INDEX IF NOT EXISTS idx_goal_interpretations_goal_entry
    ON entry_goal_interpretations(goal_id, entry_id, created_at);
CREATE INDEX IF NOT EXISTS idx_goal_changes_status ON goal_change_proposals(status, created_at);
CREATE INDEX IF NOT EXISTS idx_cleaning_style_created ON cleaning_style_profiles(created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_status_review ON decisions(status, review_date, due_date);
CREATE INDEX IF NOT EXISTS idx_decision_changes_status ON decision_change_proposals(status, created_at);
"""


@dataclass(frozen=True)
class Paths:
    root: Path
    db: Path
    originals: Path
    cleaned: Path
    weekly: Path
    drafts: Path
    backups: Path
    memory: Path


def _now() -> datetime:
    return datetime.now(TZ)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _ngrams(text: str) -> Counter[str]:
    compact = re.sub(r"\s+", "", text.casefold())
    grams = [compact[i : i + 2] for i in range(max(0, len(compact) - 1))]
    if not grams and compact:
        grams = [compact]
    return Counter(grams)


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    if not dot:
        return 0.0
    return dot / math.sqrt(sum(v * v for v in left.values()) * sum(v * v for v in right.values()))


def _text_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a string or list of strings")
    result = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _iso_date(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


class DiaryStore:
    def __init__(self, root: str | Path | None = None):
        root_path = Path(root or Path.cwd()).resolve()
        self.paths = Paths(
            root=root_path,
            db=root_path / "data" / "diary.sqlite3",
            originals=root_path / "journals" / "originals",
            cleaned=root_path / "journals" / "cleaned",
            weekly=root_path / "journals" / "weekly",
            drafts=root_path / "data" / "drafts",
            backups=root_path / "data" / "backups",
            memory=root_path / "memory",
        )

    def initialize(self) -> dict[str, str]:
        for path in (
            self.paths.db.parent,
            self.paths.originals,
            self.paths.cleaned,
            self.paths.weekly,
            self.paths.drafts,
            self.paths.backups,
            self.paths.memory,
        ):
            path.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            self._migrate_schema(db)
            db.commit()
        memory_files = {
            "user-preferences.md": "# User Preferences\n\n",
            "workflow-feedback.md": "# Workflow Feedback\n\n",
            "workflow-decisions.md": "# Workflow Decisions\n\n",
            "skill-change-history.md": "# Skill Change History\n\n",
            "goals.md": "# Goals\n\nNo confirmed goals.\n",
            "cleaning-style.md": (
                "# Cleaning Style Profile\n\n"
                "No profile yet. Until enough confirmed original entries exist, preserve the user's wording verbatim unless obvious speech artifacts require minimal cleaning.\n"
            ),
        }
        for name, content in memory_files.items():
            path = self.paths.memory / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        return {"root": str(self.paths.root), "database": str(self.paths.db)}

    def _migrate_schema(self, db: sqlite3.Connection) -> None:
        """Apply additive, idempotent migrations without rewriting journal files."""
        entries_sql = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='entries'"
        ).fetchone()
        if entries_sql and "'decision'" not in str(entries_sql["sql"]):
            db.commit()
            db.execute("PRAGMA foreign_keys=OFF")
            try:
                db.executescript(
                    """
                    BEGIN;
                    CREATE TABLE entries_new (
                        id TEXT PRIMARY KEY,
                        entry_type TEXT NOT NULL CHECK(entry_type IN ('diary','weekly','thought','decision')),
                        status TEXT NOT NULL CHECK(status IN ('draft','preview','confirmed','cancelled')),
                        raw_text TEXT NOT NULL,
                        clean_text TEXT,
                        entry_date TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'codex',
                        preview_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        confirmed_at TEXT
                    );
                    INSERT INTO entries_new
                        SELECT id,entry_type,status,raw_text,clean_text,entry_date,source,preview_json,created_at,updated_at,confirmed_at
                        FROM entries;
                    DROP TABLE entries;
                    ALTER TABLE entries_new RENAME TO entries;
                    COMMIT;
                    """
                )
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
            finally:
                db.execute("PRAGMA foreign_keys=ON")
            foreign_key_errors = db.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise RuntimeError("entry type migration failed foreign-key validation")
        proposal_sql = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='theme_change_proposals'"
        ).fetchone()
        if proposal_sql and "add_segment_tag" not in str(proposal_sql["sql"]):
            db.executescript(
                """
                CREATE TABLE theme_change_proposals_new (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL CHECK(action IN ('create','activate','deactivate','rename','merge','split','reassign_segment','add_segment_tag','remove_segment_tag')),
                    source_theme_id TEXT REFERENCES themes(id),
                    target_theme_id TEXT REFERENCES themes(id),
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','approved','rejected','applied')),
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    applied_at TEXT
                );
                INSERT INTO theme_change_proposals_new
                    SELECT * FROM theme_change_proposals;
                DROP TABLE theme_change_proposals;
                ALTER TABLE theme_change_proposals_new RENAME TO theme_change_proposals;
                CREATE INDEX IF NOT EXISTS idx_theme_changes_status
                    ON theme_change_proposals(status, created_at);
                """
            )
        goals_sql = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='goals'"
        ).fetchone()
        if goals_sql and "'long_term'" not in str(goals_sql["sql"]):
            db.commit()
            db.execute("PRAGMA foreign_keys=OFF")
            try:
                db.executescript(
                    """
                    BEGIN;
                    CREATE TABLE goals_new (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL CHECK(scope IN ('life','long_term','short_term','weekly')),
                        parent_goal_id TEXT REFERENCES goals(id),
                        title TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','paused','abandoned')),
                        priority INTEGER NOT NULL DEFAULT 0,
                        start_date TEXT,
                        target_date TEXT,
                        success_criteria TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO goals_new
                        SELECT * FROM goals;
                    DROP TABLE goals;
                    ALTER TABLE goals_new RENAME TO goals;
                    CREATE INDEX IF NOT EXISTS idx_goals_status_scope
                        ON goals(status, scope, priority);
                    COMMIT;
                    """
                )
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
            finally:
                db.execute("PRAGMA foreign_keys=ON")
            foreign_key_errors = db.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise RuntimeError("goal scope migration failed foreign-key validation")
        before = db.total_changes
        db.execute(
            """INSERT OR IGNORE INTO segment_tags(segment_id,theme_id,created_at)
               SELECT id,theme_id,? FROM segments WHERE theme_id IS NOT NULL""",
            (_iso(),),
        )
        if db.total_changes > before:
            entry_ids = [
                str(row[0])
                for row in db.execute("SELECT DISTINCT entry_id FROM segments").fetchall()
            ]
            self._refresh_entry_fts(db, entry_ids)

    def connect(self) -> sqlite3.Connection:
        self.paths.db.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.paths.db)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create_draft(self, raw_text: str, entry_type: str = "diary", source: str = "codex", entry_date: str | None = None) -> dict[str, Any]:
        self.initialize()
        if entry_type not in {"diary", "weekly", "thought", "decision"}:
            raise ValueError("entry_type must be diary, weekly, thought, or decision")
        text = raw_text.strip()
        if not text:
            raise ValueError("raw_text must not be empty")
        entry_id = str(uuid.uuid4())
        date_text = entry_date or _now().date().isoformat()
        now = _iso()
        with self.connect() as db:
            db.execute(
                "INSERT INTO entries(id,entry_type,status,raw_text,entry_date,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (entry_id, entry_type, "draft", text, date_text, source, now, now),
            )
            db.commit()
        original_path = self._journal_path("original", date_text, entry_id)
        self._write_original(original_path, entry_id, date_text, entry_type, "draft", text)
        draft_file = self.paths.drafts / f"{entry_id}.json"
        draft_file.write_text(_json({"entry_id": entry_id, "status": "draft", "created_at": now}), encoding="utf-8")
        context = self.retrieve_context(text)
        goal_context = self.conversation_context(text, token_budget=500)
        routing = self.route(text, relevant_goal_count=len(goal_context["goals"]))
        self.log_agent_run(entry_id, routing, sum(len(item["text"]) for item in context), 0)
        return {
            "entry_id": entry_id,
            "entry_date": date_text,
            "entry_type": entry_type,
            "routing_decision": routing,
            "context": context,
            "goal_context": goal_context,
            "cleaning_style": self.current_cleaning_style(),
        }

    def route(self, text: str, relevant_goal_count: int = 0) -> dict[str, Any]:
        filler_count = len(FILLER_RE.findall(text))
        punctuation = sum(text.count(mark) for mark in "，。！？；,.!?;")
        speech_like = filler_count >= 1 or (len(text) > 120 and punctuation <= 1)
        multi_topic = len(MULTI_TOPIC_RE.findall(text)) >= 2 or text.count("\n") >= 3
        uncertain = bool(UNCERTAINTY_RE.search(text))
        continuity = bool(CONTINUITY_RE.search(text))
        return {
            "stages": {
                "entry_type_classification": True,
                "clean": True,
                "classify": True,
                "continuity": True,
                "goal_interpretation": True,
            },
            "delegate": {
                "cleaner": speech_like or uncertain,
                "classifier": multi_topic,
                "continuity": continuity,
                "goal_interpreter": relevant_goal_count > 0,
            },
            "signals": {
                "filler_count": filler_count,
                "speech_like": speech_like,
                "multi_topic": multi_topic,
                "uncertain_term": uncertain,
                "continuation_language": continuity,
                "relevant_goal_count": relevant_goal_count,
                "cleaning_mode": "minimal" if speech_like or uncertain else "preserve_verbatim",
            },
            "model_preference": {
                "cleaner": "lightweight_if_supported",
                "classifier": "lightweight_if_supported",
                "continuity": "capable",
                "goal_interpreter": "capable",
                "orchestrator": "capable",
            },
        }

    def conservative_clean(self, text: str) -> str:
        source = text.strip()
        signals = self.route(source)["signals"]
        if not signals["speech_like"] and not signals["uncertain_term"]:
            return source
        cleaned = FILLER_RE.sub("", source)
        cleaned = re.sub(r"([，。！？；、])\1+", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r" *\n *", "\n", cleaned)
        return cleaned.strip(" ，")

    def _analysis_block(self, value: Any, field: str, require_judgement: bool = False) -> dict[str, Any]:
        if isinstance(value, str):
            value = {"judgement": value}
        if not isinstance(value, dict):
            raise ValueError(f"{field} must be an object or string")
        facts = _text_list(value.get("facts"), f"{field}.facts")
        assumptions = _text_list(value.get("assumptions"), f"{field}.assumptions")
        judgement = str(value.get("judgement", value.get("judgment", ""))).strip()
        if require_judgement and not judgement:
            raise ValueError(f"{field}.judgement must not be empty")
        return {"facts": facts, "assumptions": assumptions, "judgement": judgement}

    def _normalize_decision_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("decision must be an object")
        status = str(payload.get("status", payload.get("decision_status", "pending"))).strip().lower()
        if status not in DECISION_STATUSES:
            raise ValueError("decision status must be pending or made")

        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("decision objective must not be empty")

        raw_options = payload.get("options")
        if not isinstance(raw_options, (list, tuple)) or len(raw_options) < 2:
            raise ValueError("decision options must contain at least two options")
        options = []
        has_do_nothing = False
        for raw_option in raw_options:
            if isinstance(raw_option, str):
                raw_option = {"name": raw_option}
            if not isinstance(raw_option, dict):
                raise ValueError("each decision option must be an object or string")
            name = str(raw_option.get("name", raw_option.get("option", ""))).strip()
            if not name:
                raise ValueError("each decision option requires a name")
            normalized_name = _normalize(name)
            do_nothing = bool(raw_option.get("is_do_nothing")) or bool(
                re.search(r"(?:donothing|nothing|noaction|不做|不变|维持现状|不采取行动)", normalized_name)
            )
            has_do_nothing = has_do_nothing or do_nothing
            options.append(
                {
                    "name": name,
                    "is_do_nothing": do_nothing,
                    "facts": _text_list(raw_option.get("facts"), "option.facts"),
                    "assumptions": _text_list(raw_option.get("assumptions"), "option.assumptions"),
                    "reversible_consequences": _text_list(
                        raw_option.get("reversible_consequences", raw_option.get("reversible")),
                        "option.reversible_consequences",
                    ),
                    "irreversible_consequences": _text_list(
                        raw_option.get("irreversible_consequences", raw_option.get("irreversible")),
                        "option.irreversible_consequences",
                    ),
                }
            )
        if not has_do_nothing:
            raise ValueError("decision options must include a do-nothing or no-action option")

        regret = payload.get("likely_regret")
        if isinstance(regret, str):
            regret = {"one_year": regret}
        if not isinstance(regret, dict):
            raise ValueError("likely_regret must be an object or string")
        likely_regret = {
            "one_year": str(regret.get("one_year", "")).strip(),
            "five_years": str(regret.get("five_years", regret.get("five_year", ""))).strip(),
        }
        if not any(likely_regret.values()):
            raise ValueError("likely_regret must include one_year or five_years")

        experiment = payload.get("smallest_experiment")
        if isinstance(experiment, str):
            experiment = {"action": experiment}
        if not isinstance(experiment, dict):
            raise ValueError("smallest_experiment must be an object or string")
        smallest_experiment = {
            "action": str(experiment.get("action", "")).strip(),
            "uncertainty_reduced": str(experiment.get("uncertainty_reduced", "")).strip(),
            "timebox": str(experiment.get("timebox", "")).strip(),
            "success_signal": str(experiment.get("success_signal", "")).strip(),
        }
        if not smallest_experiment["action"]:
            raise ValueError("smallest_experiment.action must not be empty")

        recommendation = payload.get("recommendation")
        if not isinstance(recommendation, dict):
            if isinstance(recommendation, str):
                recommendation = {"option": recommendation}
            else:
                raise ValueError("recommendation must be an object or string")
        recommended_option = str(recommendation.get("option", recommendation.get("name", ""))).strip()
        if not recommended_option:
            raise ValueError("recommendation.option must not be empty")
        if not any(_normalize(option["name"]) == _normalize(recommended_option) for option in options):
            raise ValueError("recommendation.option must match one of the decision options")
        normalized_recommendation = {
            "option": recommended_option,
            **self._analysis_block(recommendation, "recommendation", require_judgement=True),
        }

        timeline = payload.get("timeline")
        if timeline is None:
            timeline = {}
        if not isinstance(timeline, dict):
            raise ValueError("timeline must be an object")
        review_date = _iso_date(payload.get("review_date", timeline.get("review_date")), "review_date")
        due_date = _iso_date(payload.get("due_date", timeline.get("due_date")), "due_date")
        timeline_notes = str(payload.get("timeline_notes", timeline.get("notes", ""))).strip()

        return {
            "status": status,
            "objective": objective,
            "options": options,
            "opportunity_cost": self._analysis_block(payload.get("opportunity_cost"), "opportunity_cost", require_judgement=True),
            "likely_regret": likely_regret,
            "assumptions": _text_list(payload.get("assumptions"), "assumptions"),
            "smallest_experiment": smallest_experiment,
            "recommendation": normalized_recommendation,
            "timeline": {
                "review_date": review_date,
                "due_date": due_date,
                "notes": timeline_notes,
            },
        }

    def _decision_payload_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "status": row["status"],
            "objective": row["objective"],
            "options": json.loads(row["options_json"] or "[]"),
            "opportunity_cost": json.loads(row["opportunity_cost_json"] or "{}"),
            "likely_regret": json.loads(row["likely_regret_json"] or "{}"),
            "assumptions": json.loads(row["assumptions_json"] or "[]"),
            "smallest_experiment": json.loads(row["smallest_experiment_json"] or "{}"),
            "recommendation": json.loads(row["recommendation_json"] or "{}"),
            "timeline": {
                "review_date": row["review_date"],
                "due_date": row["due_date"],
                "notes": row["timeline_notes"] or "",
            },
        }

    def _decision_search_text(self, decision: dict[str, Any]) -> str:
        return " ".join(
            str(decision.get(key) or "")
            for key in ("objective", "options", "opportunity_cost", "likely_regret", "assumptions", "smallest_experiment", "recommendation")
        )

    def _decision_record(self, db: sqlite3.Connection, entry_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """SELECT d.*,e.entry_date,e.clean_text,e.raw_text,e.source
               FROM decisions d JOIN entries e ON e.id=d.entry_id
               WHERE d.entry_id=?""",
            (entry_id,),
        ).fetchone()
        if not row:
            return None
        payload = self._decision_payload_from_row(row)
        record = {
            "decision_id": row["id"],
            "entry_id": row["entry_id"],
            "entry_date": row["entry_date"],
            "status": row["status"],
            "objective": payload["objective"],
            "options": payload["options"],
            "opportunity_cost": payload["opportunity_cost"],
            "likely_regret": payload["likely_regret"],
            "assumptions": payload["assumptions"],
            "smallest_experiment": payload["smallest_experiment"],
            "recommendation": payload["recommendation"],
            "timeline": payload["timeline"],
            "review_date": row["review_date"],
            "due_date": row["due_date"],
            "made_at": row["made_at"],
            "archived_at": row["archived_at"],
            "clean_text": row["clean_text"],
            "source": row["source"],
            "themes": self._entry_segment_records(db, str(entry_id)),
        }
        return record

    def _latest_cleaning_style(self, db: sqlite3.Connection) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT * FROM cleaning_style_profiles ORDER BY created_at DESC,id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return {
            "profile_id": row["id"],
            "profile": json.loads(row["profile_json"]),
            "sample_start": row["sample_start"],
            "sample_end": row["sample_end"],
            "updated_at": row["created_at"],
        }

    def current_cleaning_style(self) -> dict[str, Any] | None:
        self.initialize()
        with self.connect() as db:
            return self._latest_cleaning_style(db)

    def cleaning_style_context(self, char_budget: int = 8000) -> dict[str, Any]:
        """Return bounded new confirmed originals for periodic voice calibration."""
        self.initialize()
        budget = max(600, min(int(char_budget), 16000))
        with self.connect() as db:
            current = self._latest_cleaning_style(db)
            parameters: list[Any] = []
            where = "status='confirmed' AND entry_type!='weekly'"
            if current:
                where += " AND confirmed_at>?"
                parameters.append(current["updated_at"])
            rows = db.execute(
                f"""SELECT id,entry_date,raw_text,clean_text,confirmed_at
                    FROM entries WHERE {where}
                    ORDER BY confirmed_at DESC,created_at DESC LIMIT 80""",
                parameters,
            ).fetchall()

        samples: list[dict[str, Any]] = []
        used = 0
        for row in rows:
            sample_chars = len(row["raw_text"]) + len(row["clean_text"] or "")
            if samples and used + sample_chars > budget:
                continue
            samples.append(dict(row))
            used += sample_chars
            if used >= budget:
                break
        samples.reverse()
        raw_chars = sum(len(item["raw_text"]) for item in samples)
        return {
            "has_new_samples": bool(samples),
            "ready_for_review": len(samples) >= 3 and raw_chars >= 200,
            "current_style": current,
            "samples": samples,
            "sample_count": len(samples),
            "raw_chars": raw_chars,
            "char_budget": budget,
        }

    def save_cleaning_style(self, profile: dict[str, Any], source_entry_ids: list[str]) -> dict[str, Any]:
        """Persist a compact evidence-backed voice profile without rewriting journals."""
        self.initialize()
        if not isinstance(profile, dict) or not profile:
            raise ValueError("profile must be a non-empty object")
        required = {"summary", "preserve", "avoid", "observations"}
        if not required.issubset(profile):
            raise ValueError("profile requires summary, preserve, avoid, and observations")
        if not isinstance(profile["summary"], str) or not profile["summary"].strip():
            raise ValueError("profile summary must be a non-empty string")
        if not all(isinstance(profile[key], list) for key in ("preserve", "avoid", "observations")):
            raise ValueError("profile preserve, avoid, and observations must be arrays")
        if not all(isinstance(item, str) and item.strip() for key in ("preserve", "avoid") for item in profile[key]):
            raise ValueError("profile preserve and avoid items must be non-empty strings")
        for observation in profile["observations"]:
            if not isinstance(observation, dict) or not {
                "trait",
                "evidence",
            }.issubset(observation):
                raise ValueError("each observation requires trait and evidence")
            if not all(isinstance(observation[key], str) and observation[key].strip() for key in ("trait", "evidence")):
                raise ValueError("observation trait and evidence must be non-empty strings")
        serialized = _json(profile)
        if len(serialized) > 6000:
            raise ValueError("profile must stay compact")

        entry_ids = list(dict.fromkeys(str(item) for item in source_entry_ids if str(item)))
        if len(entry_ids) < 3:
            raise ValueError("at least three confirmed original entries are required")
        placeholders = ",".join("?" for _ in entry_ids)
        with self.connect() as db:
            rows = db.execute(
                f"""SELECT id,entry_date,raw_text FROM entries
                    WHERE id IN ({placeholders}) AND status='confirmed' AND entry_type!='weekly'""",
                entry_ids,
            ).fetchall()
            if len(rows) != len(entry_ids):
                raise ValueError("style evidence must use confirmed non-weekly entries")
            if sum(len(row["raw_text"]) for row in rows) < 200:
                raise ValueError("style evidence is too small; wait for more original input")
            by_id = {row["id"]: row for row in rows}
            ordered = [by_id[entry_id] for entry_id in entry_ids]
            profile_id = str(uuid.uuid4())
            now = _iso()
            db.execute(
                """INSERT INTO cleaning_style_profiles(
                       id,profile_json,source_entry_ids_json,sample_start,sample_end,created_at
                   ) VALUES(?,?,?,?,?,?)""",
                (
                    profile_id,
                    serialized,
                    _json(entry_ids),
                    min(row["entry_date"] for row in ordered),
                    max(row["entry_date"] for row in ordered),
                    now,
                ),
            )
            db.commit()

        lines = [
            "# Cleaning Style Profile",
            "",
            "This profile is derived only from confirmed verbatim originals. It guides minimal cleaning and never authorizes rewriting confirmed journals.",
            "",
            f"- Updated: {now}",
            f"- Evidence period: {min(row['entry_date'] for row in ordered)} to {max(row['entry_date'] for row in ordered)}",
            f"- Evidence entries: {', '.join(f'`{entry_id}`' for entry_id in entry_ids)}",
            "",
            "## Summary",
            "",
            profile["summary"].strip(),
            "",
            "## Preserve",
            "",
        ]
        lines.extend(f"- {item.strip()}" for item in profile["preserve"])
        lines.extend(["", "## Avoid", ""])
        lines.extend(f"- {item.strip()}" for item in profile["avoid"])
        lines.extend(["", "## Evidence-backed observations", ""])
        lines.extend(
            f"- **{item['trait'].strip()}**: {item['evidence'].strip()}"
            for item in profile["observations"]
        )
        lines.append("")
        (self.paths.memory / "cleaning-style.md").write_text("\n".join(lines), encoding="utf-8")
        return {
            "profile_id": profile_id,
            "sample_count": len(entry_ids),
            "path": str(self.paths.memory / "cleaning-style.md"),
            "updated_at": now,
        }

    def retrieve_context(
        self,
        query: str,
        token_budget: int = 1800,
        entry_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return a relevance-driven context set with no fixed item-count cap."""
        self.initialize()
        if entry_type is not None:
            entry_type = str(entry_type).strip().lower()
            if entry_type not in SEARCH_ENTRY_TYPES:
                raise ValueError("search entry_type must be diary, thought, decision, or weekly")
        char_budget = max(600, token_budget * 2)
        query_vec = _ngrams(query)
        terms = [term for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", query) if len(term) >= 2]
        candidates: dict[str, dict[str, Any]] = {}
        with self.connect() as db:
            rows: Iterable[sqlite3.Row]
            if terms:
                fts_query = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:12])
                try:
                    type_clause = " AND e.entry_type=?" if entry_type else ""
                    parameters: list[Any] = [fts_query]
                    if entry_type:
                        parameters.append(entry_type)
                    rows = db.execute(
                        f"SELECT e.*, bm25(entries_fts) AS rank FROM entries_fts JOIN entries e ON e.id=entries_fts.entry_id WHERE entries_fts MATCH ? AND e.status='confirmed'{type_clause} ORDER BY rank",
                        parameters,
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            else:
                rows = []
            for row in rows:
                candidates[row["id"]] = {**dict(row), "_fts_match": True}
            recent_sql = "SELECT * FROM entries WHERE status='confirmed'"
            recent_parameters: list[Any] = []
            if entry_type:
                recent_sql += " AND entry_type=?"
                recent_parameters.append(entry_type)
            recent_sql += " ORDER BY entry_date DESC, confirmed_at DESC"
            recent = db.execute(recent_sql, recent_parameters).fetchall()
            for row in recent:
                candidates.setdefault(row["id"], dict(row))
            for candidate in candidates.values():
                candidate["segments"] = self._entry_segment_records(db, str(candidate["id"]))
                candidate["decision"] = self._decision_record(db, str(candidate["id"]))

        scored = []
        for row in candidates.values():
            text = row.get("clean_text") or row.get("raw_text") or ""
            searchable_text = f"{text} {self._decision_search_text(row['decision'])}" if row.get("decision") else text
            semantic = _cosine(query_vec, _ngrams(searchable_text))
            days = max(0, (_now().date() - datetime.fromisoformat(row["entry_date"]).date()).days)
            recency = 1 / (1 + days / 30)
            score = semantic * 0.82 + recency * 0.18
            if row.get("_fts_match"):
                score = max(score, 0.35 + recency * 0.05)
            if semantic > 0.04 or days <= 14 or row.get("_fts_match"):
                scored.append((score, row, text))
        scored.sort(key=lambda item: item[0], reverse=True)

        selected: list[dict[str, Any]] = []
        used = 0
        covered: set[str] = set()
        previous_score = 1.0
        for score, row, text in scored:
            novelty_terms = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", text)) - covered
            marginal = score * (1.0 if novelty_terms else 0.35)
            if selected and marginal < 0.08 and score < previous_score * 0.55:
                break
            snippet = text[:1200]
            if used + len(snippet) > char_budget:
                remaining = char_budget - used
                if remaining < 160:
                    break
                snippet = snippet[:remaining]
            selected.append(
                {
                    "entry_id": row["id"],
                    "date": row["entry_date"],
                    "type": row["entry_type"],
                    "score": round(score, 4),
                    "text": snippet,
                    "segments": row.get("segments", []),
                    "decision": row.get("decision"),
                }
            )
            used += len(snippet)
            covered.update(novelty_terms)
            previous_score = score
            if used >= char_budget:
                break
        return selected

    def save_preview(
        self,
        entry_id: str,
        clean_text: str,
        segments: list[dict[str, Any]],
        uncertainties: list[dict[str, Any]] | None = None,
        links: list[dict[str, Any]] | None = None,
        followups: list[dict[str, Any]] | None = None,
        goal_interpretations: list[dict[str, Any]] | None = None,
        decision: dict[str, Any] | None = None,
        entry_type: str | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        clean = clean_text.strip()
        if not clean:
            raise ValueError("clean_text must not be empty")
        normalized_segments = []
        for position, segment in enumerate(segments):
            text = str(segment.get("text", "")).strip()
            theme = str(segment.get("theme", "")).strip()
            if not text or not theme:
                raise ValueError("each segment requires text and theme")
            raw_tags = segment.get("tags") or []
            if not isinstance(raw_tags, (list, tuple)):
                raise ValueError("segment tags must be a list")
            tags = []
            seen = {_normalize(theme)}
            for value in raw_tags:
                tag = str(value).strip()
                normalized = _normalize(tag)
                if tag and normalized not in seen:
                    tags.append(tag)
                    seen.add(normalized)
            normalized_segments.append({"position": position, "text": text, "theme": theme, "tags": tags})
        with self.connect() as db:
            current = db.execute("SELECT id,status,raw_text,entry_type FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not current:
                raise KeyError(entry_id)
            if current["status"] == "confirmed":
                raise ValueError("confirmed entries cannot be overwritten through preview")
            selected_entry_type = str(current["entry_type"])
            if entry_type is not None:
                requested_entry_type = str(entry_type).strip().lower()
                if requested_entry_type not in USER_ENTRY_TYPES:
                    raise ValueError("preview entry_type must be diary, thought, or decision")
                if selected_entry_type == "weekly":
                    raise ValueError("weekly entry types cannot be changed through user-input preview")
                selected_entry_type = requested_entry_type
            normalized_decision = None
            if selected_entry_type == "decision":
                if decision is None:
                    raise ValueError("decision entries require a structured decision preview")
                normalized_decision = self._normalize_decision_payload(decision)
            elif decision is not None:
                raise ValueError("only decision entries may include a decision payload")
            normalized_goal_interpretations = self._validate_goal_interpretations(
                db,
                current,
                clean,
                goal_interpretations or [],
            )
            preview = {
                "entry_type": selected_entry_type,
                "clean_text": clean,
                "segments": normalized_segments,
                "uncertainties": uncertainties or [],
                "links": links or [],
                "followups": followups or [],
                "goal_interpretations": normalized_goal_interpretations,
            }
            if normalized_decision is not None:
                preview["decision"] = normalized_decision
            db.execute(
                "UPDATE entries SET entry_type=?,status='preview',clean_text=?,preview_json=?,updated_at=? WHERE id=?",
                (selected_entry_type, clean, _json(preview), _iso(), entry_id),
            )
            db.commit()
        (self.paths.drafts / f"{entry_id}.json").write_text(_json({"entry_id": entry_id, "status": "preview", "preview": preview}), encoding="utf-8")
        return {"entry_id": entry_id, "status": "preview", "preview": preview}

    def confirm(self, entry_id: str) -> dict[str, Any]:
        self.initialize()
        with self.connect() as db:
            row = db.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not row:
                raise KeyError(entry_id)
            if row["status"] == "confirmed":
                return {"entry_id": entry_id, "status": "confirmed", "idempotent": True}
            if row["status"] != "preview" or not row["clean_text"]:
                raise ValueError("entry must have a preview before confirmation")
            preview = json.loads(row["preview_json"])
            decision_payload = None
            if row["entry_type"] == "decision":
                if not isinstance(preview.get("decision"), dict):
                    raise ValueError("decision entries require a structured decision preview")
                decision_payload = self._normalize_decision_payload(preview["decision"])
            goal_interpretations = self._validate_goal_interpretations(
                db,
                row,
                str(row["clean_text"]),
                preview.get("goal_interpretations") or [],
            )
            preview["goal_interpretations"] = goal_interpretations
            db.execute("DELETE FROM segments WHERE entry_id=?", (entry_id,))
            theme_names = []
            stored_segments = []
            for segment in preview.get("segments", []):
                theme_id = self._ensure_theme(db, segment["theme"])
                theme = self._canonical_theme_row(db, theme_id)
                if not theme or theme["status"] != "active":
                    raise ValueError(f"theme is not active: {segment['theme']}")
                theme_name = str(theme["name"])
                if theme_name not in theme_names:
                    theme_names.append(theme_name)
                tag_rows = []
                seen_theme_ids = {str(theme["id"])}
                for tag_name in segment.get("tags") or []:
                    tag_id = self._ensure_theme(db, str(tag_name))
                    tag = self._canonical_theme_row(db, tag_id)
                    if not tag or tag["status"] != "active":
                        raise ValueError(f"tag is not active: {tag_name}")
                    if str(tag["id"]) not in seen_theme_ids:
                        tag_rows.append(tag)
                        seen_theme_ids.add(str(tag["id"]))
                        if str(tag["name"]) not in theme_names:
                            theme_names.append(str(tag["name"]))
                stored_segments.append({**segment, "theme": theme_name, "tags": [str(tag["name"]) for tag in tag_rows]})
                segment_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO segments(id,entry_id,position,text,theme_id,theme_name) VALUES(?,?,?,?,?,?)",
                    (segment_id, entry_id, segment["position"], segment["text"], theme["id"], theme_name),
                )
                for tagged_theme_id in seen_theme_ids:
                    db.execute(
                        "INSERT INTO segment_tags(segment_id,theme_id,created_at) VALUES(?,?,?)",
                        (segment_id, tagged_theme_id, _iso()),
                    )
            db.execute("DELETE FROM entry_goal_interpretations WHERE entry_id=?", (entry_id,))
            for interpretation in goal_interpretations:
                db.execute(
                    """INSERT INTO entry_goal_interpretations
                       (id,entry_id,goal_id,goal_title,relation,evidence,interpretation,feedback,confidence,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(uuid.uuid4()),
                        entry_id,
                        interpretation["goal_id"],
                        interpretation["goal_title"],
                        interpretation["relation"],
                        interpretation["evidence"],
                        interpretation["interpretation"],
                        interpretation["feedback"],
                        interpretation["confidence"],
                        _iso(),
                    ),
                )
            for link in preview.get("links", []):
                target = str(link.get("target_entry_id", ""))
                if target and db.execute("SELECT 1 FROM entries WHERE id=?", (target,)).fetchone():
                    db.execute(
                        "INSERT OR IGNORE INTO entry_links(id,source_entry_id,target_entry_id,relation,reason,score,created_at) VALUES(?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), entry_id, target, link.get("relation", "related"), link.get("reason", ""), float(link.get("score", 0)), _iso()),
                    )
            for followup in preview.get("followups", []):
                question = str(followup.get("question", "")).strip()
                if question:
                    db.execute(
                        "INSERT INTO followups(id,entry_id,question,status,revisit_after,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), entry_id, question, followup.get("status", "pending"), followup.get("revisit_after"), _iso(), _iso()),
                    )
            confirmed_at = _iso()
            decision_id = None
            if decision_payload is not None:
                decision_id = str(uuid.uuid4())
                made_at = confirmed_at if decision_payload["status"] == "made" else None
                archived_at = made_at
                decision_payload = {
                    **decision_payload,
                    "decision_id": decision_id,
                    "made_at": made_at,
                    "archived_at": archived_at,
                }
                timeline = decision_payload["timeline"]
                db.execute(
                    """INSERT INTO decisions(
                           id,entry_id,status,objective,options_json,opportunity_cost_json,likely_regret_json,
                           assumptions_json,smallest_experiment_json,recommendation_json,review_date,due_date,
                           timeline_notes,made_at,archived_at,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        decision_id,
                        entry_id,
                        decision_payload["status"],
                        decision_payload["objective"],
                        _json(decision_payload["options"]),
                        _json(decision_payload["opportunity_cost"]),
                        _json(decision_payload["likely_regret"]),
                        _json(decision_payload["assumptions"]),
                        _json(decision_payload["smallest_experiment"]),
                        _json(decision_payload["recommendation"]),
                        timeline["review_date"],
                        timeline["due_date"],
                        timeline["notes"],
                        made_at,
                        archived_at,
                        confirmed_at,
                        confirmed_at,
                    ),
                )
            preview = {**preview, "segments": stored_segments}
            if decision_payload is not None:
                preview["decision"] = decision_payload
            db.execute("UPDATE entries SET status='confirmed',preview_json=?,confirmed_at=?,updated_at=? WHERE id=?", (_json(preview), confirmed_at, confirmed_at, entry_id))
            db.execute("DELETE FROM entries_fts WHERE entry_id=?", (entry_id,))
            db.execute("INSERT INTO entries_fts(entry_id,clean_text,themes) VALUES(?,?,?)", (entry_id, row["clean_text"], " ".join(theme_names)))
            db.commit()
            result = dict(row)
            result.update(status="confirmed", confirmed_at=confirmed_at, themes=theme_names)
        original_path = self._journal_path("original", result["entry_date"], entry_id)
        self._write_original(original_path, entry_id, result["entry_date"], result["entry_type"], "confirmed", result["raw_text"])
        clean_path = self._journal_path("weekly" if result["entry_type"] == "weekly" else "cleaned", result["entry_date"], entry_id)
        self._write_clean(clean_path, result, preview)
        draft_file = self.paths.drafts / f"{entry_id}.json"
        if draft_file.exists():
            draft_file.unlink()
        return {"entry_id": entry_id, "status": "confirmed", "idempotent": False, "original_path": str(original_path), "clean_path": str(clean_path)}

    def update_followup(self, followup_id: str, status: str, answer: str | None = None, revisit_after: str | None = None) -> dict[str, Any]:
        if status not in {"answered", "skipped", "deferred"}:
            raise ValueError("invalid followup status")
        with self.connect() as db:
            cursor = db.execute("UPDATE followups SET status=?,answer=?,revisit_after=?,updated_at=? WHERE id=?", (status, answer, revisit_after, _iso(), followup_id))
            db.commit()
            if not cursor.rowcount:
                raise KeyError(followup_id)
        return {"followup_id": followup_id, "status": status}

    def add_feedback(self, content: str, kind: str = "inconvenience", source_entry_id: str | None = None) -> dict[str, Any]:
        self.initialize()
        feedback_id = str(uuid.uuid4())
        created = _iso()
        with self.connect() as db:
            db.execute("INSERT INTO feedback_events(id,content,kind,source_entry_id,created_at) VALUES(?,?,?,?,?)", (feedback_id, content.strip(), kind, source_entry_id, created))
            db.commit()
        path = self.paths.memory / "workflow-feedback.md"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"## {created} [{kind}]\n\n- ID: `{feedback_id}`\n- {content.strip()}\n\n")
        return {"feedback_id": feedback_id, "status": "new"}

    def weekly_context(self, now: datetime | None = None) -> dict[str, Any]:
        self.initialize()
        moment = (now or _now()).astimezone(TZ)
        this_monday = (moment - timedelta(days=moment.weekday())).date()
        start = this_monday - timedelta(days=7)
        end = this_monday - timedelta(days=1)
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,entry_type,entry_date,clean_text,preview_json FROM entries WHERE status='confirmed' AND entry_type!='weekly' AND entry_date BETWEEN ? AND ? ORDER BY entry_date,created_at",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            records = []
            for row in rows:
                records.append(
                    {
                        "entry_id": row["id"],
                        "entry_type": row["entry_type"],
                        "date": row["entry_date"],
                        "clean_text": row["clean_text"],
                        "segments": self._entry_segment_records(db, str(row["id"])),
                        "decision": self._decision_record(db, str(row["id"])),
                    }
                )
            goals = self._weekly_goal_context(db, start.isoformat(), end.isoformat())
            historical = self._weekly_historical_context(db, start.isoformat(), end.isoformat(), records, goals)
            pending_decisions = self._pending_decisions(db, moment.date())
            decision_review = self._decision_review_payload(pending_decisions, moment.date())
        diary_entries = [item for item in records if item["entry_type"] == "diary"]
        thought_entries = [item for item in records if item["entry_type"] == "thought"]
        return {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "has_content": bool(records or pending_decisions),
            "has_journal_content": bool(records),
            "has_diary_content": bool(diary_entries),
            "has_thought_content": bool(thought_entries),
            "entries": records,
            "diary_entries": diary_entries,
            "thought_entries": thought_entries,
            "goals": goals,
            "pending_decisions": pending_decisions,
            "decision_review": decision_review,
            "historical_connections": historical["connections"],
            "historical_query_signals": historical["query_signals"],
            "reflection_prompt_candidate": historical["reflection_prompt_candidate"],
            "theme_review": self.theme_review_context(moment),
        }

    def _pending_decisions(self, db: sqlite3.Connection, reference_date: Any) -> list[dict[str, Any]]:
        reference = reference_date if hasattr(reference_date, "isoformat") else datetime.fromisoformat(str(reference_date)).date()
        rows = db.execute(
            """SELECT d.id,e.id AS entry_id FROM decisions d JOIN entries e ON e.id=d.entry_id
               WHERE d.status='pending' AND e.status='confirmed'
               ORDER BY COALESCE(d.due_date,d.review_date,'9999-12-31'),e.entry_date,d.created_at"""
        ).fetchall()
        records = []
        for row in rows:
            record = self._decision_record(db, str(row["entry_id"]))
            if not record:
                continue
            trigger_candidates = [
                (value, label)
                for label, value in (("review_date", record.get("review_date")), ("due_date", record.get("due_date")))
                if value
            ]
            if not trigger_candidates:
                reminder = "unscheduled"
                days_until = None
                trigger = None
                trigger_kind = None
            else:
                trigger, trigger_kind = min(trigger_candidates, key=lambda item: item[0])
                trigger_date = datetime.fromisoformat(str(trigger)).date()
                days_until = (trigger_date - reference).days
                if days_until < 0:
                    reminder = "overdue"
                elif days_until <= 7:
                    reminder = "due_soon"
                else:
                    reminder = "scheduled"
            record["reminder"] = reminder
            record["days_until_review_or_due"] = days_until
            record["next_trigger"] = trigger
            record["next_trigger_kind"] = trigger_kind
            records.append(record)
        return records

    def _decision_review_payload(self, pending_decisions: list[dict[str, Any]], reference_date: Any) -> dict[str, Any]:
        reminders = [item for item in pending_decisions if item["reminder"] in {"overdue", "due_soon"}]
        suggestions = []
        for item in pending_decisions:
            if item["reminder"] == "overdue":
                action = "Finalize it, defer it with a new date, or run the smallest experiment."
            elif item["reminder"] == "due_soon":
                action = "Prepare the structured comparison and confirm whether the timeline still holds."
            elif item["reminder"] == "unscheduled":
                action = "Set a review date or explicitly keep it pending."
            else:
                action = "Keep the decision visible and revisit it at the scheduled review."
            suggestions.append(
                {
                    "decision_id": item["decision_id"],
                    "objective": item["objective"],
                    "reminder": item["reminder"],
                    "suggested_action": action,
                }
            )
        return {
            "has_pending": bool(pending_decisions),
            "reference_date": reference_date.isoformat() if hasattr(reference_date, "isoformat") else str(reference_date),
            "reminders": reminders,
            "suggestions": suggestions,
            "review_template": list(DECISION_STRUCTURE),
            "instruction": (
                "For each pending decision, complete the objective, options including doing nothing, "
                "reversible and irreversible consequences, opportunity cost, one- or five-year regret, "
                "fallible assumptions, smallest experiment, and one recommendation. Label facts, assumptions, and judgement separately."
            ),
        }

    def decision_review_context(self, now: datetime | None = None) -> dict[str, Any]:
        self.initialize()
        moment = (now or _now()).astimezone(TZ)
        with self.connect() as db:
            pending = self._pending_decisions(db, moment.date())
        return self._decision_review_payload(pending, moment.date()) | {"pending_decisions": pending}

    def decision_context(self, query: str | None = None, status: str = "pending") -> dict[str, Any]:
        self.initialize()
        if status not in {"pending", "made", "all"}:
            raise ValueError("decision status must be pending, made, or all")
        with self.connect() as db:
            sql = "SELECT d.entry_id FROM decisions d JOIN entries e ON e.id=d.entry_id WHERE e.status='confirmed'"
            params: list[Any] = []
            if status != "all":
                sql += " AND d.status=?"
                params.append(status)
            sql += " ORDER BY d.updated_at DESC"
            rows = db.execute(sql, params).fetchall()
            records = [self._decision_record(db, str(row["entry_id"])) for row in rows]
        records = [item for item in records if item]
        if query:
            vector = _ngrams(query)
            records = [
                item for item in records
                if _cosine(vector, _ngrams(self._decision_search_text(item))) >= 0.08
                or _normalize(query) in _normalize(self._decision_search_text(item))
            ]
        return {"has_decisions": bool(records), "status": status, "decisions": records}

    def decision_change_preview(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        self.initialize()
        if not isinstance(changes, (list, tuple)) or not changes:
            raise ValueError("changes must not be empty")
        created = []
        with self.connect() as db:
            for item in changes:
                if not isinstance(item, dict):
                    raise ValueError("each decision change must be an object")
                action = str(item.get("action", "")).strip()
                if action not in {"update", "make", "reopen"}:
                    raise ValueError("decision change action must be update, make, or reopen")
                decision_id = str(item.get("decision_id", "")).strip()
                current = db.execute(
                    """SELECT d.*,e.status AS entry_status,e.entry_date FROM decisions d
                       JOIN entries e ON e.id=d.entry_id WHERE d.id=?""",
                    (decision_id,),
                ).fetchone()
                if not current:
                    raise KeyError(decision_id)
                if current["entry_status"] != "confirmed":
                    raise ValueError("decision changes require a confirmed decision entry")
                payload = item.get("payload") or {}
                if not isinstance(payload, dict):
                    raise ValueError("decision change payload must be an object")
                if isinstance(payload.get("decision"), dict):
                    payload = payload["decision"]
                base = self._decision_payload_from_row(current)
                merged = dict(base)
                for key in ("objective", "options", "opportunity_cost", "likely_regret", "assumptions", "smallest_experiment", "recommendation"):
                    if key in payload:
                        merged[key] = payload[key]
                if "timeline" in payload:
                    merged["timeline"] = payload["timeline"]
                for key in ("review_date", "due_date", "timeline_notes"):
                    if key in payload:
                        merged[key] = payload[key]
                normalized = self._normalize_decision_payload(merged)
                if action == "make":
                    normalized["status"] = "made"
                elif action == "reopen":
                    normalized["status"] = "pending"
                else:
                    normalized["status"] = current["status"]
                proposal_id = str(uuid.uuid4())
                now = _iso()
                db.execute(
                    """INSERT INTO decision_change_proposals(
                           id,decision_id,action,payload_json,evidence_json,status,created_at
                       ) VALUES(?,?,?,?,?,'proposed',?)""",
                    (
                        proposal_id,
                        decision_id,
                        action,
                        _json({"decision": normalized}),
                        _json(item.get("evidence") or []),
                        now,
                    ),
                )
                created.append(
                    {
                        "proposal_id": proposal_id,
                        "decision_id": decision_id,
                        "action": action,
                        "decision": normalized,
                        "evidence": item.get("evidence") or [],
                        "status": "proposed",
                    }
                )
            db.commit()
        return {"proposals": created, "requires_confirmation": True}

    def _apply_decision_change(self, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        current = db.execute(
            "SELECT d.*,e.preview_json,e.entry_date,e.entry_type FROM decisions d JOIN entries e ON e.id=d.entry_id WHERE d.id=?",
            (row["decision_id"],),
        ).fetchone()
        if not current:
            raise KeyError(str(row["decision_id"]))
        payload = json.loads(row["payload_json"] or "{}").get("decision")
        normalized = self._normalize_decision_payload(payload or {})
        now = _iso()
        made_at = current["made_at"]
        archived_at = current["archived_at"]
        if normalized["status"] == "made" and not made_at:
            made_at = now
            archived_at = now
        db.execute(
            """UPDATE decisions SET status=?,objective=?,options_json=?,opportunity_cost_json=?,likely_regret_json=?,
                       assumptions_json=?,smallest_experiment_json=?,recommendation_json=?,review_date=?,due_date=?,
                       timeline_notes=?,made_at=?,archived_at=?,updated_at=? WHERE id=?""",
            (
                normalized["status"],
                normalized["objective"],
                _json(normalized["options"]),
                _json(normalized["opportunity_cost"]),
                _json(normalized["likely_regret"]),
                _json(normalized["assumptions"]),
                _json(normalized["smallest_experiment"]),
                _json(normalized["recommendation"]),
                normalized["timeline"]["review_date"],
                normalized["timeline"]["due_date"],
                normalized["timeline"]["notes"],
                made_at,
                archived_at,
                now,
                row["decision_id"],
            ),
        )
        preview = json.loads(current["preview_json"] or "{}")
        preview["decision"] = {
            **normalized,
            "decision_id": current["id"],
            "made_at": made_at,
            "archived_at": archived_at,
        }
        db.execute("UPDATE entries SET preview_json=?,updated_at=? WHERE id=?", (_json(preview), now, current["entry_id"]))
        return {
            "decision_id": current["id"],
            "entry_id": current["entry_id"],
            "decision_status": normalized["status"],
            "made_at": made_at,
            "archived_at": archived_at,
        }

    def apply_decision_changes(self, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        self.initialize()
        if not isinstance(decisions, (list, tuple)) or not decisions:
            raise ValueError("decisions must not be empty")
        results = []
        changed_entries: set[str] = set()
        with self.connect() as db:
            for decision in decisions:
                proposal_id = str(decision.get("proposal_id", ""))
                verdict = str(decision.get("decision", ""))
                if verdict not in {"approved", "rejected"}:
                    raise ValueError("each decision must be approved or rejected")
                row = db.execute("SELECT * FROM decision_change_proposals WHERE id=?", (proposal_id,)).fetchone()
                if not row:
                    raise KeyError(proposal_id)
                if row["status"] in {"applied", "rejected"}:
                    results.append({"proposal_id": proposal_id, "status": row["status"], "idempotent": True})
                    continue
                now = _iso()
                if verdict == "rejected":
                    db.execute("UPDATE decision_change_proposals SET status='rejected',decided_at=? WHERE id=?", (now, proposal_id))
                    results.append({"proposal_id": proposal_id, "status": "rejected", "idempotent": False})
                    continue
                details = self._apply_decision_change(db, row)
                db.execute("UPDATE decision_change_proposals SET status='applied',decided_at=?,applied_at=? WHERE id=?", (now, now, proposal_id))
                changed_entries.add(str(details["entry_id"]))
                results.append({"proposal_id": proposal_id, "status": "applied", "idempotent": False, **details})
            db.commit()
        for entry_id in changed_entries:
            with self.connect() as db:
                entry = db.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            if entry:
                preview = json.loads(entry["preview_json"] or "{}")
                clean_path = self._journal_path("weekly" if entry["entry_type"] == "weekly" else "cleaned", entry["entry_date"], entry_id)
                self._write_clean(clean_path, dict(entry), preview)
        return {"results": results}

    def _weekly_historical_context(
        self,
        db: sqlite3.Connection,
        start: str,
        end: str,
        current_entries: list[dict[str, Any]],
        goals: list[dict[str, Any]],
        token_budget: int = 900,
    ) -> dict[str, Any]:
        if not current_entries:
            return {"connections": [], "query_signals": {"themes": [], "terms": []}, "reflection_prompt_candidate": None}
        current_entry_ids = {str(item["entry_id"]) for item in current_entries}
        current_text = " ".join(str(item.get("clean_text") or "") for item in current_entries)
        goal_parts = []
        for item in goals:
            goal_parts.extend(str(item.get(key) or "") for key in ("title", "description", "success_criteria"))
            for evidence in item.get("weekly_evidence", []):
                goal_parts.extend([str(evidence.get("evidence") or ""), str(evidence.get("clean_text") or "")])
            for interpretation in item.get("weekly_interpretations", []):
                goal_parts.extend(
                    [
                        str(interpretation.get("evidence") or ""),
                        str(interpretation.get("interpretation") or ""),
                        str(interpretation.get("feedback") or ""),
                    ]
                )
            for event in item.get("weekly_events", []):
                goal_parts.extend([_json(event.get("payload") or {}), _json(event.get("evidence") or [])])
        goal_text = " ".join(goal_parts)
        current_theme_ids: set[str] = set()
        current_theme_names: list[str] = []
        tagged = db.execute(
            """SELECT DISTINCT st.theme_id FROM segment_tags st
               JOIN segments s ON s.id=st.segment_id JOIN entries e ON e.id=s.entry_id
               WHERE e.status='confirmed' AND e.entry_date BETWEEN ? AND ?""",
            (start, end),
        ).fetchall()
        for row in tagged:
            theme = self._canonical_theme_row(db, str(row["theme_id"]))
            if theme and theme["status"] == "active":
                current_theme_ids.add(str(theme["id"]))
                if str(theme["name"]) not in current_theme_names:
                    current_theme_names.append(str(theme["name"]))
        raw_terms = re.findall(r"[A-Za-z0-9_]{3,}|[\u4e00-\u9fff]{2,8}", f"{current_text} {goal_text}")
        terms = []
        for term in raw_terms:
            normalized = _normalize(term)
            if normalized and normalized not in {_normalize(value) for value in terms}:
                terms.append(term)
            if len(terms) >= 16:
                break
        fts_entry_ids: set[str] = set()
        fts_terms = [*current_theme_names, *terms][:12]
        if fts_terms:
            fts_query = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in fts_terms)
            try:
                fts_entry_ids = {
                    str(row[0])
                    for row in db.execute(
                        """SELECT entry_id FROM entries_fts
                           JOIN entries e ON e.id=entries_fts.entry_id
                           WHERE entries_fts MATCH ? AND e.status='confirmed'
                           AND e.entry_type!='weekly' AND e.entry_date<?""",
                        (fts_query, start),
                    ).fetchall()
                }
            except sqlite3.OperationalError:
                fts_entry_ids = set()
        linked_entry_ids: set[str] = set()
        if current_entry_ids:
            placeholders = ",".join("?" for _ in current_entry_ids)
            link_rows = db.execute(
                f"""SELECT source_entry_id,target_entry_id FROM entry_links
                    WHERE source_entry_id IN ({placeholders}) OR target_entry_id IN ({placeholders})""",
                (*current_entry_ids, *current_entry_ids),
            ).fetchall()
            for link in link_rows:
                for linked_id in (str(link["source_entry_id"]), str(link["target_entry_id"])):
                    if linked_id not in current_entry_ids:
                        linked_entry_ids.add(linked_id)
        query_vector = _ngrams(" ".join([current_text, goal_text, *current_theme_names]))
        candidates = []
        rows = db.execute(
            """SELECT s.*,e.entry_date,e.clean_text FROM segments s
               JOIN entries e ON e.id=s.entry_id
               WHERE e.status='confirmed' AND e.entry_type!='weekly' AND e.entry_date<?
               ORDER BY e.entry_date DESC,s.position""",
            (start,),
        ).fetchall()
        start_date = datetime.fromisoformat(start).date()
        for row in rows:
            candidate_theme_ids: set[str] = set()
            candidate_theme_names: list[str] = []
            for tagged_row in db.execute("SELECT theme_id FROM segment_tags WHERE segment_id=?", (row["id"],)).fetchall():
                theme = self._canonical_theme_row(db, str(tagged_row["theme_id"]))
                if theme and theme["status"] == "active":
                    candidate_theme_ids.add(str(theme["id"]))
                    if str(theme["name"]) not in candidate_theme_names:
                        candidate_theme_names.append(str(theme["name"]))
            overlap_ids = current_theme_ids & candidate_theme_ids
            semantic = _cosine(query_vector, _ngrams(str(row["text"])))
            fts_match = str(row["entry_id"]) in fts_entry_ids
            linked = str(row["entry_id"]) in linked_entry_ids
            if not (overlap_ids or linked or (fts_match and semantic >= 0.10) or semantic >= 0.22):
                continue
            days = max(1, (start_date - datetime.fromisoformat(str(row["entry_date"])).date()).days)
            recency = 1 / (1 + days / 90)
            overlap = len(overlap_ids) / max(1, len(current_theme_ids))
            score = semantic * 0.55 + overlap * 0.30 + (0.10 if linked else 0.0) + recency * 0.05
            reasons = []
            if overlap_ids:
                shared_names = [
                    name
                    for name in candidate_theme_names
                    if any(
                        theme_id in overlap_ids
                        and (theme := self._canonical_theme_row(db, theme_id)) is not None
                        and str(theme["name"]) == name
                        for theme_id in overlap_ids
                    )
                ]
                reasons.append({"kind": "shared_themes", "values": shared_names})
            if fts_match:
                reasons.append({"kind": "fts_term_match"})
            if semantic >= 0.10:
                reasons.append({"kind": "ngram_similarity", "score": round(semantic, 4)})
            if linked:
                reasons.append({"kind": "entry_link"})
            segment_record = self._entry_segment_records(db, str(row["entry_id"]))
            record = next((item for item in segment_record if item["segment_id"] == row["id"]), None)
            if not record:
                continue
            candidates.append(
                {
                    "entry_id": row["entry_id"],
                    "segment_id": row["id"],
                    "date": row["entry_date"],
                    "text": row["text"],
                    "theme": record["theme"],
                    "tags": record["tags"],
                    "score": round(score, 4),
                    "semantic_score": round(semantic, 4),
                    "evidence_reasons": reasons,
                }
            )
        candidates.sort(key=lambda item: (item["score"], item["date"], item["segment_id"]), reverse=True)
        selected = []
        used = 0
        char_budget = max(600, token_budget * 2)
        for candidate in candidates:
            if any(_cosine(_ngrams(candidate["text"]), _ngrams(item["text"])) >= 0.92 for item in selected):
                continue
            size = len(candidate["text"]) + len(_json(candidate["evidence_reasons"])) + 80
            if selected and used + size > char_budget:
                break
            selected.append(candidate)
            used += size
            if used >= char_budget:
                break
        prompt_candidate = None
        if selected:
            top = selected[0]
            reason_kinds = {item["kind"] for item in top["evidence_reasons"]}
            if top["score"] >= 0.32 and top["semantic_score"] >= 0.10 and reason_kinds & {"shared_themes", "entry_link"}:
                prompt_candidate = {
                    "current_period": {"start": start, "end": end},
                    "historical_entry_id": top["entry_id"],
                    "historical_segment_id": top["segment_id"],
                    "reason": "strong evidence of a related pattern or unfinished thread",
                    "suggested_focus": "pattern_change_blocker_or_unfinished_thread",
                }
        return {
            "connections": selected,
            "query_signals": {"themes": current_theme_names, "terms": terms},
            "reflection_prompt_candidate": prompt_candidate,
        }

    def theme_review_context(self, now: datetime | None = None) -> dict[str, Any]:
        self.initialize()
        moment = (now or _now()).astimezone(TZ)
        recent_start = (moment.date() - timedelta(days=90)).isoformat()
        with self.connect() as db:
            rows = db.execute(
                """SELECT t.*, COUNT(st.segment_id) AS total_uses,
                   SUM(CASE WHEN e.entry_date>=? THEN 1 ELSE 0 END) AS recent_uses
                   FROM themes t
                   LEFT JOIN segment_tags st ON st.theme_id=t.id
                   LEFT JOIN segments s ON s.id=st.segment_id
                   LEFT JOIN entries e ON e.id=s.entry_id AND e.status='confirmed'
                   GROUP BY t.id ORDER BY t.status, total_uses DESC, t.name""",
                (recent_start,),
            ).fetchall()
            themes: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                representatives = db.execute(
                    """SELECT s.id AS segment_id,s.entry_id,e.entry_date,s.text
                       FROM segment_tags st JOIN segments s ON s.id=st.segment_id
                       JOIN entries e ON e.id=s.entry_id
                       WHERE st.theme_id=? AND e.status='confirmed'
                       ORDER BY e.entry_date DESC,s.position LIMIT 3""",
                    (row["id"],),
                ).fetchall()
                item["representative_segments"] = [dict(value) for value in representatives]
                item["aliases"] = json.loads(item.pop("aliases_json") or "[]")
                themes.append(item)
            active = [item for item in themes if item["status"] == "active"]
            overlaps = []
            for index, left in enumerate(active):
                for right in active[index + 1 :]:
                    score = _cosine(_ngrams(left["name"]), _ngrams(right["name"]))
                    if score >= 0.55:
                        overlaps.append({"left_theme_id": left["id"], "right_theme_id": right["id"], "score": round(score, 4), "reason": "similar theme names"})
            total_segments = sum(int(item["total_uses"] or 0) for item in active)
            broad_threshold = max(4, math.ceil(total_segments * 0.25))
            broad = [
                {"theme_id": item["id"], "name": item["name"], "total_uses": item["total_uses"], "reason": "high share of tagged segments"}
                for item in active
                if int(item["total_uses"] or 0) >= broad_threshold
            ]
            pending = db.execute(
                "SELECT * FROM theme_change_proposals WHERE status='proposed' ORDER BY created_at"
            ).fetchall()
        return {
            "recent_start": recent_start,
            "active": active,
            "inactive": [item for item in themes if item["status"] == "inactive"],
            "merged": [item for item in themes if item["status"] == "merged"],
            "possible_overlaps": overlaps,
            "possibly_broad": broad,
            "pending_proposals": [self._decode_proposal(row) for row in pending],
        }

    def save_theme_review(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        self.initialize()
        allowed = {"create", "activate", "deactivate", "rename", "merge", "split", "reassign_segment", "add_segment_tag", "remove_segment_tag"}
        if not changes:
            raise ValueError("changes must not be empty")
        created = []
        with self.connect() as db:
            for change in changes:
                action = str(change.get("action", ""))
                if action not in allowed:
                    raise ValueError(f"invalid theme action: {action}")
                source = change.get("source_theme_id")
                target = change.get("target_theme_id")
                payload = dict(change.get("payload") or {})
                evidence = change.get("evidence") or []
                if action not in {"create", "reassign_segment", "add_segment_tag"} and not source:
                    raise ValueError(f"{action} requires source_theme_id")
                if action == "merge" and not target:
                    raise ValueError("merge requires target_theme_id")
                if action == "add_segment_tag" and not (target or payload.get("target_theme_id")):
                    raise ValueError("add_segment_tag requires target_theme_id")
                if action in {"reassign_segment", "add_segment_tag", "remove_segment_tag"}:
                    segment_id = str(payload.get("segment_id", ""))
                    if not segment_id or not db.execute("SELECT 1 FROM segments WHERE id=?", (segment_id,)).fetchone():
                        raise KeyError(segment_id)
                if source and not db.execute("SELECT 1 FROM themes WHERE id=?", (source,)).fetchone():
                    raise KeyError(str(source))
                if target and not db.execute("SELECT 1 FROM themes WHERE id=?", (target,)).fetchone():
                    raise KeyError(str(target))
                proposal_id = str(uuid.uuid4())
                now = _iso()
                db.execute(
                    """INSERT INTO theme_change_proposals
                       (id,action,source_theme_id,target_theme_id,payload_json,evidence_json,status,created_at)
                       VALUES(?,?,?,?,?,?, 'proposed',?)""",
                    (proposal_id, action, source, target, _json(payload), _json(evidence), now),
                )
                created.append({"proposal_id": proposal_id, "action": action, "status": "proposed", "payload": payload, "evidence": evidence})
            db.commit()
        return {"proposals": created, "requires_confirmation": True}

    def apply_theme_changes(self, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        self.initialize()
        if not decisions:
            raise ValueError("decisions must not be empty")
        results = []
        with self.connect() as db:
            for decision in decisions:
                proposal_id = str(decision.get("proposal_id", ""))
                verdict = str(decision.get("decision", ""))
                if verdict not in {"approved", "rejected"}:
                    raise ValueError("each decision must be approved or rejected")
                row = db.execute("SELECT * FROM theme_change_proposals WHERE id=?", (proposal_id,)).fetchone()
                if not row:
                    raise KeyError(proposal_id)
                if row["status"] in {"applied", "rejected"}:
                    results.append({"proposal_id": proposal_id, "status": row["status"], "idempotent": True})
                    continue
                now = _iso()
                if verdict == "rejected":
                    db.execute("UPDATE theme_change_proposals SET status='rejected',decided_at=? WHERE id=?", (now, proposal_id))
                    results.append({"proposal_id": proposal_id, "status": "rejected", "idempotent": False})
                    continue
                db.execute("UPDATE theme_change_proposals SET status='approved',decided_at=? WHERE id=?", (now, proposal_id))
                details = self._apply_theme_change(db, row)
                applied_at = _iso()
                db.execute("UPDATE theme_change_proposals SET status='applied',applied_at=? WHERE id=?", (applied_at, proposal_id))
                results.append({"proposal_id": proposal_id, "status": "applied", "idempotent": False, **details})
            db.commit()
        return {"results": results}

    def goal_change_preview(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        self.initialize()
        allowed = {"create", "update", "complete", "pause", "abandon", "activate", "link_entry"}
        if not changes:
            raise ValueError("changes must not be empty")
        refs: dict[str, str] = {}
        normalized: list[dict[str, Any]] = []
        for change in changes:
            action = str(change.get("action", ""))
            if action not in allowed:
                raise ValueError(f"invalid goal action: {action}")
            payload = dict(change.get("payload") or {})
            if action == "create":
                goal_id = str(change.get("goal_id") or payload.get("goal_id") or uuid.uuid4())
                payload["goal_id"] = goal_id
                if change.get("ref"):
                    refs[str(change["ref"])] = goal_id
            normalized.append({"action": action, "goal_id": change.get("goal_id") or payload.get("goal_id"), "payload": payload, "evidence": change.get("evidence") or []})
        for original, item in zip(changes, normalized):
            payload = item["payload"]
            if original.get("goal_ref"):
                item["goal_id"] = refs.get(str(original["goal_ref"]), str(original["goal_ref"]))
            if original.get("parent_ref"):
                payload["parent_goal_id"] = refs.get(str(original["parent_ref"]), str(original["parent_ref"]))
        created = []
        with self.connect() as db:
            for item in normalized:
                proposal_id = str(uuid.uuid4())
                now = _iso()
                db.execute(
                    """INSERT INTO goal_change_proposals
                       (id,action,goal_id,payload_json,evidence_json,status,created_at)
                       VALUES(?,?,?,?,?,'proposed',?)""",
                    (proposal_id, item["action"], item["goal_id"], _json(item["payload"]), _json(item["evidence"]), now),
                )
                created.append({"proposal_id": proposal_id, **item, "status": "proposed"})
            db.commit()
        return {"proposals": created, "requires_confirmation": True}

    def apply_goal_changes(self, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        self.initialize()
        if not decisions:
            raise ValueError("decisions must not be empty")
        results = []
        approved: list[sqlite3.Row] = []
        with self.connect() as db:
            for decision in decisions:
                proposal_id = str(decision.get("proposal_id", ""))
                verdict = str(decision.get("decision", ""))
                if verdict not in {"approved", "rejected"}:
                    raise ValueError("each decision must be approved or rejected")
                row = db.execute("SELECT * FROM goal_change_proposals WHERE id=?", (proposal_id,)).fetchone()
                if not row:
                    raise KeyError(proposal_id)
                if row["status"] in {"applied", "rejected"}:
                    results.append({"proposal_id": proposal_id, "status": row["status"], "idempotent": True})
                    continue
                now = _iso()
                if verdict == "rejected":
                    db.execute("UPDATE goal_change_proposals SET status='rejected',decided_at=? WHERE id=?", (now, proposal_id))
                    results.append({"proposal_id": proposal_id, "status": "rejected", "idempotent": False})
                else:
                    db.execute("UPDATE goal_change_proposals SET status='approved',decided_at=? WHERE id=?", (now, proposal_id))
                    approved.append(row)
            pending = list(approved)
            while pending:
                progressed = False
                for row in list(pending):
                    try:
                        details = self._apply_goal_change(db, row)
                    except KeyError:
                        continue
                    applied_at = _iso()
                    db.execute("UPDATE goal_change_proposals SET status='applied',applied_at=? WHERE id=?", (applied_at, row["id"]))
                    results.append({"proposal_id": row["id"], "status": "applied", "idempotent": False, **details})
                    pending.remove(row)
                    progressed = True
                if not progressed:
                    missing = ", ".join(str(row["goal_id"]) for row in pending)
                    raise ValueError(f"approved goal changes have missing dependencies: {missing}")
            db.commit()
        if any(item["status"] == "applied" and not item.get("idempotent") for item in results):
            self._write_goals_mirror()
        return {"results": results, "goals_path": str(self.paths.memory / "goals.md")}

    def goal_context(self, query: str | None = None, status: str = "active") -> dict[str, Any]:
        self.initialize()
        allowed_statuses = {"active", "completed", "paused", "abandoned", "all"}
        if status not in allowed_statuses:
            raise ValueError("invalid goal status")
        with self.connect() as db:
            sql = "SELECT * FROM goals"
            params: list[Any] = []
            if status != "all":
                sql += " WHERE status=?"
                params.append(status)
            sql += " ORDER BY priority DESC, scope, created_at"
            rows = db.execute(sql, params).fetchall()
            records = [self._goal_record(db, row) for row in rows]
        if query:
            vector = _ngrams(query)
            records = [item for item in records if _cosine(vector, _ngrams(self._goal_search_text(item))) >= 0.08 or _normalize(query) in _normalize(self._goal_search_text(item))]
        return {"has_goals": bool(records), "goals": records}

    def conversation_context(self, query: str, token_budget: int = 700) -> dict[str, Any]:
        self.initialize()
        text = query.strip()
        if not text:
            raise ValueError("query must not be empty")
        vector = _ngrams(text)
        scored = []
        with self.connect() as db:
            rows = db.execute("SELECT * FROM goals WHERE status='active' ORDER BY priority DESC,updated_at DESC").fetchall()
            for row in rows:
                record = self._goal_record(db, row, event_limit=3, evidence_limit=3)
                haystack = self._goal_search_text(record)
                score = _cosine(vector, _ngrams(haystack))
                if _normalize(text) in _normalize(haystack) or _normalize(row["title"]) in _normalize(text):
                    score = max(score, 0.75)
                if score >= 0.08:
                    scored.append((score, record))
        scored.sort(key=lambda item: (item[0], item[1]["priority"]), reverse=True)
        budget = max(300, token_budget * 2)
        selected = []
        used = 0
        for score, record in scored:
            size = len(_json(record))
            if selected and used + size > budget:
                break
            record["relevance_score"] = round(score, 4)
            selected.append(record)
            used += size
        return {"has_context": bool(selected), "query": text, "goals": selected}

    def _validate_goal_interpretations(
        self,
        db: sqlite3.Connection,
        entry: sqlite3.Row,
        clean_text: str,
        interpretations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not isinstance(interpretations, (list, tuple)):
            raise ValueError("goal_interpretations must be a list")
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        entry_text = f"{entry['raw_text']}\n{clean_text}".strip()
        field_limits = {"evidence": 500, "interpretation": 500, "feedback": 300}
        for item in interpretations:
            if not isinstance(item, dict):
                raise ValueError("each goal interpretation must be an object")
            goal_id = str(item.get("goal_id") or "").strip()
            goal = db.execute("SELECT id,title,status FROM goals WHERE id=?", (goal_id,)).fetchone()
            if not goal:
                raise ValueError(f"unknown goal for interpretation: {goal_id or '<missing>'}")
            if goal["status"] != "active":
                raise ValueError(f"goal interpretation requires an active goal: {goal_id}")
            relation = str(item.get("relation") or "").strip()
            if relation not in {"progress", "blocker", "reflection", "related"}:
                raise ValueError(f"invalid goal interpretation relation: {relation or '<missing>'}")
            fields = {name: str(item.get(name) or "").strip() for name in field_limits}
            for name, limit in field_limits.items():
                if not fields[name]:
                    raise ValueError(f"goal interpretation requires {name}")
                if len(fields[name]) > limit:
                    raise ValueError(f"goal interpretation {name} exceeds {limit} characters")
            evidence_normalized = _normalize(fields["evidence"])
            entry_normalized = _normalize(entry_text)
            faithful_score = _cosine(_ngrams(fields["evidence"]), _ngrams(entry_text))
            if evidence_normalized not in entry_normalized and faithful_score < 0.18:
                raise ValueError("goal interpretation evidence must come from the current entry")
            confidence = item.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise ValueError("goal interpretation confidence must be a number from 0 to 1")
            confidence_value = float(confidence)
            if not math.isfinite(confidence_value) or not 0 <= confidence_value <= 1:
                raise ValueError("goal interpretation confidence must be a number from 0 to 1")
            key = (goal_id, relation, evidence_normalized)
            if key in seen:
                raise ValueError("duplicate goal interpretation")
            seen.add(key)
            normalized.append(
                {
                    "goal_id": goal_id,
                    "goal_title": str(goal["title"])[:200],
                    "relation": relation,
                    **fields,
                    "confidence": confidence_value,
                    "ai_generated": True,
                    "authoritative": False,
                }
            )
        return normalized

    def _decode_proposal(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        return item

    def _apply_theme_change(self, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        action = str(row["action"])
        payload = json.loads(row["payload_json"] or "{}")
        source_id = row["source_theme_id"]
        target_id = row["target_theme_id"]
        affected_entries: set[str] = set()
        if source_id:
            affected_entries.update(value[0] for value in db.execute("SELECT DISTINCT entry_id FROM segments WHERE theme_id=?", (source_id,)).fetchall())
            affected_entries.update(
                value[0]
                for value in db.execute(
                    "SELECT DISTINCT s.entry_id FROM segment_tags st JOIN segments s ON s.id=st.segment_id WHERE st.theme_id=?",
                    (source_id,),
                ).fetchall()
            )
        if action == "create":
            created = self._create_theme(db, payload)
            return {"theme_ids": [created["id"]]}
        if action == "reassign_segment":
            segment_id = str(payload.get("segment_id", ""))
            segment = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
            if not segment:
                raise KeyError(segment_id)
            chosen_target = target_id or payload.get("target_theme_id")
            target = self._canonical_theme_row(db, str(chosen_target)) if chosen_target else None
            if not target or target["status"] != "active":
                raise ValueError("reassign_segment requires an active target theme")
            db.execute("DELETE FROM segment_tags WHERE segment_id=? AND theme_id=?", (segment_id, segment["theme_id"]))
            db.execute("UPDATE segments SET theme_id=?,theme_name=? WHERE id=?", (target["id"], target["name"], segment_id))
            db.execute(
                "INSERT OR IGNORE INTO segment_tags(segment_id,theme_id,created_at) VALUES(?,?,?)",
                (segment_id, target["id"], _iso()),
            )
            self._refresh_entry_fts(db, {str(segment["entry_id"])})
            return {"segment_id": segment_id, "theme_ids": [target["id"]]}
        if action in {"add_segment_tag", "remove_segment_tag"}:
            segment_id = str(payload.get("segment_id", ""))
            segment = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
            if not segment:
                raise KeyError(segment_id)
            if action == "add_segment_tag":
                requested_id = target_id or payload.get("target_theme_id")
            else:
                requested_id = source_id or payload.get("source_theme_id")
            requested = db.execute("SELECT * FROM themes WHERE id=?", (requested_id,)).fetchone() if requested_id else None
            canonical = self._canonical_theme_row(db, str(requested_id)) if requested_id else None
            if not requested or not canonical:
                raise KeyError(str(requested_id))
            if action == "add_segment_tag":
                if canonical["status"] != "active":
                    raise ValueError("add_segment_tag requires an active target theme")
                db.execute(
                    "INSERT OR IGNORE INTO segment_tags(segment_id,theme_id,created_at) VALUES(?,?,?)",
                    (segment_id, canonical["id"], _iso()),
                )
            else:
                primary = self._canonical_theme_row(db, str(segment["theme_id"])) if segment["theme_id"] else None
                if primary and primary["id"] == canonical["id"]:
                    raise ValueError("remove_segment_tag cannot remove the primary theme")
                db.execute(
                    "DELETE FROM segment_tags WHERE segment_id=? AND theme_id IN (?,?)",
                    (segment_id, requested["id"], canonical["id"]),
                )
            self._refresh_entry_fts(db, {str(segment["entry_id"])})
            return {"segment_id": segment_id, "theme_ids": [str(canonical["id"])]}
        source = db.execute("SELECT * FROM themes WHERE id=?", (source_id,)).fetchone()
        if not source:
            raise KeyError(str(source_id))
        if action == "activate":
            db.execute("UPDATE themes SET status='active',merged_into=NULL,updated_at=? WHERE id=?", (_iso(), source_id))
        elif action == "deactivate":
            db.execute("UPDATE themes SET status='inactive',merged_into=NULL,updated_at=? WHERE id=?", (_iso(), source_id))
        elif action == "rename":
            name = str(payload.get("name", "")).strip()
            if not name:
                raise ValueError("rename requires payload.name")
            conflict = db.execute("SELECT id FROM themes WHERE normalized_name=? AND id<>?", (_normalize(name), source_id)).fetchone()
            if conflict:
                raise ValueError("theme name already exists")
            aliases = json.loads(source["aliases_json"] or "[]")
            if source["name"] not in aliases:
                aliases.append(source["name"])
            db.execute("UPDATE themes SET name=?,normalized_name=?,aliases_json=?,updated_at=? WHERE id=?", (name, _normalize(name), _json(aliases), _iso(), source_id))
        elif action == "merge":
            target = self._canonical_theme_row(db, str(target_id))
            if not target or target["status"] != "active" or target["id"] == source_id:
                raise ValueError("merge requires a different active target theme")
            db.execute("UPDATE themes SET status='merged',merged_into=?,updated_at=? WHERE id=?", (target["id"], _iso(), source_id))
        elif action == "split":
            new_themes = payload.get("themes") or payload.get("new_themes") or []
            if len(new_themes) < 2:
                raise ValueError("split requires at least two new themes")
            created_ids = []
            for item in new_themes:
                values = {"name": item} if isinstance(item, str) else dict(item)
                created_ids.append(self._create_theme(db, values)["id"])
            db.execute("UPDATE themes SET status='inactive',merged_into=NULL,updated_at=? WHERE id=?", (_iso(), source_id))
            self._refresh_entry_fts(db, affected_entries)
            return {"theme_ids": created_ids, "source_theme_id": source_id}
        else:
            raise ValueError(action)
        self._refresh_entry_fts(db, affected_entries)
        return {"theme_ids": [str(source_id)]}

    def _create_theme(self, db: sqlite3.Connection, payload: dict[str, Any]) -> sqlite3.Row:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("theme creation requires a name")
        if db.execute("SELECT 1 FROM themes WHERE normalized_name=?", (_normalize(name),)).fetchone():
            raise ValueError("theme name already exists")
        theme_id = str(payload.get("theme_id") or uuid.uuid4())
        now = _iso()
        db.execute(
            "INSERT INTO themes(id,name,normalized_name,description,aliases_json,status,created_at,updated_at) VALUES(?,?,?,?,?,'active',?,?)",
            (theme_id, name, _normalize(name), str(payload.get("description", "")), _json(payload.get("aliases") or []), now, now),
        )
        return db.execute("SELECT * FROM themes WHERE id=?", (theme_id,)).fetchone()

    def _canonical_theme_row(self, db: sqlite3.Connection, theme_id: str) -> sqlite3.Row | None:
        current = db.execute("SELECT * FROM themes WHERE id=?", (theme_id,)).fetchone()
        seen = set()
        while current and current["status"] == "merged" and current["merged_into"]:
            if current["id"] in seen:
                raise ValueError("theme merge cycle detected")
            seen.add(current["id"])
            current = db.execute("SELECT * FROM themes WHERE id=?", (current["merged_into"],)).fetchone()
        return current

    def _entry_segment_records(self, db: sqlite3.Connection, entry_id: str) -> list[dict[str, Any]]:
        records = []
        rows = db.execute("SELECT * FROM segments WHERE entry_id=? ORDER BY position", (entry_id,)).fetchall()
        for row in rows:
            primary = self._canonical_theme_row(db, str(row["theme_id"])) if row["theme_id"] else None
            primary_name = str(primary["name"]) if primary and primary["status"] == "active" else str(row["theme_name"])
            tags = []
            for tagged in db.execute("SELECT theme_id FROM segment_tags WHERE segment_id=?", (row["id"],)).fetchall():
                theme = self._canonical_theme_row(db, str(tagged["theme_id"]))
                if theme and theme["status"] == "active" and str(theme["name"]) != primary_name and str(theme["name"]) not in tags:
                    tags.append(str(theme["name"]))
            tags.sort(key=_normalize)
            records.append(
                {
                    "segment_id": row["id"],
                    "position": row["position"],
                    "text": row["text"],
                    "theme": primary_name,
                    "tags": tags,
                }
            )
        return records

    def _refresh_entry_fts(self, db: sqlite3.Connection, entry_ids: Iterable[str]) -> None:
        for entry_id in set(entry_ids):
            entry = db.execute("SELECT clean_text,status FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not entry or entry["status"] != "confirmed":
                continue
            names = []
            tagged_themes = db.execute(
                """SELECT st.theme_id FROM segment_tags st
                   JOIN segments s ON s.id=st.segment_id
                   WHERE s.entry_id=? ORDER BY s.position,st.created_at""",
                (entry_id,),
            ).fetchall()
            for tagged in tagged_themes:
                theme = self._canonical_theme_row(db, str(tagged["theme_id"]))
                if theme and theme["status"] == "active" and theme["name"] not in names:
                    names.append(str(theme["name"]))
            db.execute("DELETE FROM entries_fts WHERE entry_id=?", (entry_id,))
            db.execute("INSERT INTO entries_fts(entry_id,clean_text,themes) VALUES(?,?,?)", (entry_id, entry["clean_text"] or "", " ".join(names)))

    def _apply_goal_change(self, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        action = str(row["action"])
        goal_id = str(row["goal_id"] or "")
        payload = json.loads(row["payload_json"] or "{}")
        evidence = json.loads(row["evidence_json"] or "[]")
        now = _iso()
        if action == "create":
            goal_id = str(payload.get("goal_id") or goal_id or uuid.uuid4())
            scope = str(payload.get("scope", ""))
            title = str(payload.get("title", "")).strip()
            if scope not in GOAL_SCOPE_RANK or not title:
                raise ValueError("goal creation requires scope and title")
            parent = payload.get("parent_goal_id")
            self._validate_goal_parent(db, goal_id, scope, parent)
            db.execute(
                """INSERT INTO goals(id,scope,parent_goal_id,title,description,status,priority,start_date,target_date,success_criteria,created_at,updated_at)
                   VALUES(?,?,?,?,?,'active',?,?,?,?,?,?)""",
                (goal_id, scope, parent, title, str(payload.get("description", "")), int(payload.get("priority", 0)), payload.get("start_date"), payload.get("target_date"), str(payload.get("success_criteria", "")), now, now),
            )
            event_type = "created"
        else:
            current = db.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
            if not current:
                raise KeyError(goal_id)
            if action == "update":
                allowed = {"scope", "parent_goal_id", "title", "description", "priority", "start_date", "target_date", "success_criteria"}
                updates = {key: value for key, value in payload.items() if key in allowed}
                if not updates:
                    raise ValueError("update has no supported fields")
                scope = str(updates.get("scope", current["scope"]))
                parent = updates.get("parent_goal_id", current["parent_goal_id"])
                self._validate_goal_parent(db, goal_id, scope, parent)
                if "title" in updates and not str(updates["title"]).strip():
                    raise ValueError("goal title must not be empty")
                updates["updated_at"] = now
                columns = ",".join(f"{key}=?" for key in updates)
                db.execute(f"UPDATE goals SET {columns} WHERE id=?", (*updates.values(), goal_id))
                event_type = "updated"
            elif action == "link_entry":
                entry_id = str(payload.get("entry_id", ""))
                relation = str(payload.get("relation", "related"))
                entry = db.execute("SELECT status FROM entries WHERE id=?", (entry_id,)).fetchone()
                if not entry or entry["status"] != "confirmed":
                    raise ValueError("goal evidence must link a confirmed entry")
                if relation not in {"progress", "blocker", "reflection", "related"}:
                    raise ValueError("invalid goal-entry relation")
                link_id = str(uuid.uuid4())
                db.execute(
                    "INSERT OR IGNORE INTO goal_entry_links(id,goal_id,entry_id,relation,evidence,created_at) VALUES(?,?,?,?,?,?)",
                    (link_id, goal_id, entry_id, relation, str(payload.get("evidence", "")), now),
                )
                event_type = "entry_linked"
            else:
                statuses = {"complete": "completed", "pause": "paused", "abandon": "abandoned", "activate": "active"}
                status = statuses[action]
                db.execute("UPDATE goals SET status=?,updated_at=? WHERE id=?", (status, now, goal_id))
                payload = {**payload, "status": status}
                event_type = "status_changed"
        db.execute(
            "INSERT INTO goal_events(id,goal_id,event_type,payload_json,evidence_json,created_at) VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), goal_id, event_type, _json(payload), _json(evidence), now),
        )
        return {"goal_id": goal_id, "event_type": event_type}

    def _validate_goal_parent(self, db: sqlite3.Connection, goal_id: str, scope: str, parent_goal_id: str | None) -> None:
        if scope not in GOAL_SCOPE_RANK:
            raise ValueError("invalid goal scope")
        if scope == "life" and parent_goal_id:
            raise ValueError("life goals cannot have a parent")
        if not parent_goal_id:
            return
        if parent_goal_id == goal_id:
            raise ValueError("a goal cannot parent itself")
        parent = db.execute("SELECT scope,parent_goal_id FROM goals WHERE id=?", (parent_goal_id,)).fetchone()
        if not parent:
            raise KeyError(str(parent_goal_id))
        if GOAL_SCOPE_RANK[str(parent["scope"])] >= GOAL_SCOPE_RANK[scope]:
            raise ValueError("parent goal must have a broader scope")
        ancestor = parent
        seen = {goal_id}
        while ancestor:
            ancestor_id = ancestor["parent_goal_id"]
            if not ancestor_id:
                break
            if ancestor_id in seen:
                raise ValueError("goal hierarchy cycle detected")
            seen.add(str(ancestor_id))
            ancestor = db.execute("SELECT scope,parent_goal_id FROM goals WHERE id=?", (ancestor_id,)).fetchone()

    def _goal_record(self, db: sqlite3.Connection, row: sqlite3.Row, event_limit: int = 5, evidence_limit: int = 5) -> dict[str, Any]:
        item = dict(row)
        events = db.execute("SELECT event_type,payload_json,evidence_json,created_at FROM goal_events WHERE goal_id=? ORDER BY created_at DESC LIMIT ?", (row["id"], event_limit)).fetchall()
        links = db.execute(
            """SELECT l.entry_id,l.relation,l.evidence,l.created_at,e.entry_date,e.clean_text
               FROM goal_entry_links l JOIN entries e ON e.id=l.entry_id
               WHERE l.goal_id=? ORDER BY e.entry_date DESC,l.created_at DESC LIMIT ?""",
            (row["id"], evidence_limit),
        ).fetchall()
        item["recent_events"] = [{**dict(event), "payload": json.loads(event["payload_json"] or "{}"), "evidence": json.loads(event["evidence_json"] or "[]")} for event in events]
        for event in item["recent_events"]:
            event.pop("payload_json", None)
            event.pop("evidence_json", None)
        item["evidence"] = [dict(link) for link in links]
        return item

    def _goal_search_text(self, goal: dict[str, Any]) -> str:
        evidence = " ".join(str(item.get("evidence") or item.get("clean_text") or "") for item in goal.get("evidence", []))
        return " ".join(str(goal.get(key) or "") for key in ("title", "description", "success_criteria")) + " " + evidence

    def _weekly_goal_context(self, db: sqlite3.Connection, start: str, end: str) -> list[dict[str, Any]]:
        rows = db.execute("SELECT * FROM goals WHERE status='active' ORDER BY priority DESC,scope,created_at").fetchall()
        records = []
        for row in rows:
            item = dict(row)
            evidence = db.execute(
                """SELECT l.entry_id,l.relation,l.evidence,e.entry_date,e.clean_text
                   FROM goal_entry_links l JOIN entries e ON e.id=l.entry_id
                   WHERE l.goal_id=? AND e.entry_date BETWEEN ? AND ? ORDER BY e.entry_date""",
                (row["id"], start, end),
            ).fetchall()
            interpretations = db.execute(
                """SELECT i.entry_id,i.goal_title AS goal_title_snapshot,i.relation,i.evidence,
                          i.interpretation,i.feedback,i.confidence,i.created_at,e.entry_date
                   FROM entry_goal_interpretations i JOIN entries e ON e.id=i.entry_id
                   WHERE i.goal_id=? AND e.status='confirmed' AND e.entry_date BETWEEN ? AND ?
                   ORDER BY e.entry_date,i.created_at""",
                (row["id"], start, end),
            ).fetchall()
            events = db.execute("SELECT event_type,payload_json,evidence_json,created_at FROM goal_events WHERE goal_id=? AND substr(created_at,1,10) BETWEEN ? AND ? ORDER BY created_at", (row["id"], start, end)).fetchall()
            item["weekly_evidence"] = [dict(value) for value in evidence]
            item["weekly_interpretations"] = [
                {
                    **dict(value),
                    "source_type": "ai_goal_interpretation",
                    "authoritative": False,
                }
                for value in interpretations
            ]
            item["weekly_events"] = [{**dict(value), "payload": json.loads(value["payload_json"] or "{}"), "evidence": json.loads(value["evidence_json"] or "[]")} for value in events]
            for event in item["weekly_events"]:
                event.pop("payload_json", None)
                event.pop("evidence_json", None)
            records.append(item)
        return records

    def _write_goals_mirror(self) -> None:
        with self.connect() as db:
            goals = db.execute("SELECT * FROM goals ORDER BY scope,priority DESC,created_at").fetchall()
            events = db.execute(
                """SELECT ge.event_type,ge.created_at,g.title,ge.payload_json
                   FROM goal_events ge JOIN goals g ON g.id=ge.goal_id
                   ORDER BY ge.created_at DESC LIMIT 12"""
            ).fetchall()
        lines = ["# Goals", "", "SQLite is the source of truth. This file is regenerated only after confirmed goal changes.", ""]
        for scope in GOAL_SCOPES:
            lines.extend([f"## {GOAL_SCOPE_LABELS[scope]}", ""])
            scoped = [row for row in goals if row["scope"] == scope]
            if not scoped:
                lines.extend(["- None", ""])
                continue
            for row in scoped:
                target = f"; target {row['target_date']}" if row["target_date"] else ""
                parent = f"; parent `{row['parent_goal_id']}`" if row["parent_goal_id"] else ""
                lines.append(f"- [{row['status']}] **{row['title']}** (priority {row['priority']}{target}{parent})")
                if row["description"]:
                    lines.append(f"  - {row['description']}")
                if row["success_criteria"]:
                    lines.append(f"  - Success: {row['success_criteria']}")
            lines.append("")
        lines.extend(["## Recent confirmed changes", ""])
        if not events:
            lines.append("- None")
        else:
            for event in events:
                lines.append(f"- {event['created_at']}: {event['title']} — {event['event_type']}")
        lines.append("")
        (self.paths.memory / "goals.md").write_text("\n".join(lines), encoding="utf-8")

    def feedback_review_context(self, now: datetime | None = None) -> dict[str, Any]:
        moment = (now or _now()).astimezone(TZ)
        start = (moment - timedelta(days=7)).isoformat(timespec="seconds")
        with self.connect() as db:
            rows = db.execute("SELECT id,content,kind,created_at FROM feedback_events WHERE status='new' AND created_at>=? ORDER BY created_at", (start,)).fetchall()
        return {"has_feedback": bool(rows), "feedback": [dict(row) for row in rows]}

    def propose_skill_revision(self, proposal: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        revision_id = str(uuid.uuid4())
        now = _iso()
        with self.connect() as db:
            db.execute("INSERT INTO skill_revisions(id,status,proposal_json,created_at,updated_at) VALUES(?,?,?,?,?)", (revision_id, "proposed", _json(proposal), now, now))
            feedback_ids = [str(item) for item in proposal.get("feedback_ids", [])]
            for feedback_id in feedback_ids:
                db.execute("UPDATE feedback_events SET status='planned',revision_id=? WHERE id=?", (revision_id, feedback_id))
            db.commit()
        proposal_path = self.paths.memory / f"skill-proposal-{revision_id}.json"
        proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
        commit = self.git_snapshot(f"chore(diary): snapshot skill proposal {revision_id[:8]}")
        with self.connect() as db:
            db.execute("UPDATE skill_revisions SET git_before_commit=?,updated_at=? WHERE id=?", (commit, _iso(), revision_id))
            db.commit()
        # The commit itself contains the database state before git_before_commit is written;
        # persist that audit pointer in a small follow-up metadata commit.
        metadata_commit = self.git_snapshot(f"chore(diary): record proposal snapshot {revision_id[:8]}")
        push = self.git_push_current_branch()
        return {
            "revision_id": revision_id,
            "status": "proposed",
            "snapshot_commit": commit,
            "metadata_commit": metadata_commit,
            "push": push,
            "proposal_path": str(proposal_path),
        }

    def mark_skill_revision(self, revision_id: str, status: str, test_summary: str = "") -> dict[str, Any]:
        if status not in {"approved", "applied", "rejected", "failed"}:
            raise ValueError("invalid revision status")
        with self.connect() as db:
            row = db.execute("SELECT proposal_json FROM skill_revisions WHERE id=?", (revision_id,)).fetchone()
            if not row:
                raise KeyError(revision_id)
            db.execute("UPDATE skill_revisions SET status=?,updated_at=? WHERE id=?", (status, _iso(), revision_id))
            db.commit()
        history = self.paths.memory / "skill-change-history.md"
        with history.open("a", encoding="utf-8") as handle:
            handle.write(f"## {_iso()} {status}\n\n- Revision: `{revision_id}`\n- Tests: {test_summary or 'not supplied'}\n\n")
        commit = None
        metadata_commit = None
        push = None
        if status in {"applied", "failed", "rejected"}:
            commit = self.git_snapshot(f"chore(diary): {status} skill revision {revision_id[:8]}")
            with self.connect() as db:
                db.execute("UPDATE skill_revisions SET git_after_commit=?,updated_at=? WHERE id=?", (commit, _iso(), revision_id))
                db.commit()
            metadata_commit = self.git_snapshot(f"chore(diary): record revision result {revision_id[:8]}")
            push = self.git_push_current_branch()
        return {
            "revision_id": revision_id,
            "status": status,
            "commit": commit,
            "metadata_commit": metadata_commit,
            "push": push,
        }

    def search(
        self,
        query: str,
        token_budget: int = 1800,
        entry_type: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.retrieve_context(query, token_budget=token_budget, entry_type=entry_type)

    def backup(self) -> dict[str, str]:
        self.initialize()
        stamp = _now().strftime("%Y%m%d-%H%M%S")
        destination = self.paths.backups / f"diary-{stamp}.sqlite3"
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        manifest = destination.with_suffix(".sha256")
        manifest.write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
        return {"database": str(destination), "sha256": digest, "manifest": str(manifest)}

    def git_snapshot(self, message: str) -> str:
        """Commit the complete local state, including the main DB and all journals."""
        if self.paths.db.exists():
            with sqlite3.connect(self.paths.db) as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if not (self.paths.root / ".git").exists():
            subprocess.run(["git", "init"], cwd=self.paths.root, check=True, capture_output=True, text=True)
        identity = (
            ("user.name", "Diary Agent"),
            ("user.email", "diary-agent@local.invalid"),
        )
        for key, fallback in identity:
            current = subprocess.run(
                ["git", "config", "--local", "--get", key],
                cwd=self.paths.root,
                check=False,
                capture_output=True,
                text=True,
            )
            if not current.stdout.strip():
                subprocess.run(
                    ["git", "config", "--local", key, fallback],
                    cwd=self.paths.root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
        subprocess.run(["git", "add", "-A"], cwd=self.paths.root, check=True, capture_output=True, text=True)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=self.paths.root)
        if staged.returncode == 0:
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.paths.root, check=False, capture_output=True, text=True)
            return head.stdout.strip() if head.returncode == 0 else ""
        result = subprocess.run(["git", "commit", "-m", message], cwd=self.paths.root, check=True, capture_output=True, text=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.paths.root, check=True, capture_output=True, text=True)
        return head.stdout.strip()

    def git_push_current_branch(self) -> dict[str, str]:
        """Push HEAD to its upstream, establishing origin when needed."""
        branch_result = subprocess.run(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            cwd=self.paths.root,
            check=False,
            capture_output=True,
            text=True,
        )
        branch = branch_result.stdout.strip()
        if branch_result.returncode != 0 or not branch:
            raise RuntimeError("cannot publish diary changes from a detached Git HEAD")

        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            cwd=self.paths.root,
            check=False,
            capture_output=True,
            text=True,
        )
        if upstream.returncode == 0 and upstream.stdout.strip():
            remote = subprocess.run(
                ["git", "config", "--get", f"branch.{branch}.remote"],
                cwd=self.paths.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            push_args = ["git", "push"]
        else:
            remotes = subprocess.run(
                ["git", "remote"],
                cwd=self.paths.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.split()
            if not remotes:
                raise RuntimeError("cannot publish diary changes because no Git remote is configured")
            if "origin" in remotes:
                remote = "origin"
            elif len(remotes) == 1:
                remote = remotes[0]
            else:
                raise RuntimeError("cannot choose a Git remote; configure an upstream for the current branch")
            push_args = ["git", "push", "--set-upstream", remote, branch]

        pushed = subprocess.run(
            push_args,
            cwd=self.paths.root,
            check=False,
            capture_output=True,
            text=True,
        )
        if pushed.returncode != 0:
            detail = (pushed.stderr or pushed.stdout).strip()
            raise RuntimeError(f"git push failed: {detail or 'unknown error'}")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.paths.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return {"commit": head, "remote": remote, "branch": branch}

    def git_publish(self, message: str) -> dict[str, Any]:
        """Commit the complete repository state and push the current branch."""
        commit = self.git_snapshot(message)
        return {"commit": commit, "push": self.git_push_current_branch()}

    def log_agent_run(self, entry_id: str | None, routing: dict[str, Any], context_chars: int, output_chars: int) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO agent_runs(id,entry_id,routing_json,context_chars,output_chars,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), entry_id, _json(routing), context_chars, output_chars, _iso()))
            db.commit()

    def _ensure_theme(self, db: sqlite3.Connection, name: str) -> str:
        normalized = _normalize(name)
        row = db.execute("SELECT * FROM themes WHERE normalized_name=?", (normalized,)).fetchone()
        if row:
            if row["status"] == "inactive":
                raise ValueError(f"inactive theme must be activated before reuse: {name}")
            canonical = self._canonical_theme_row(db, str(row["id"]))
            if not canonical or canonical["status"] != "active":
                raise ValueError(f"theme does not resolve to an active theme: {name}")
            return str(canonical["id"])
        theme_id = str(uuid.uuid4())
        now = _iso()
        db.execute("INSERT INTO themes(id,name,normalized_name,created_at,updated_at) VALUES(?,?,?,?,?)", (theme_id, name.strip(), normalized, now, now))
        return theme_id

    def _journal_path(self, kind: str, date_text: str, entry_id: str) -> Path:
        date_value = datetime.fromisoformat(date_text).date()
        if kind == "original":
            base = self.paths.originals / f"{date_value.year:04d}" / f"{date_value.month:02d}"
        elif kind == "weekly":
            base = self.paths.weekly / f"{date_value.year:04d}"
        else:
            base = self.paths.cleaned / f"{date_value.year:04d}" / f"{date_value.month:02d}"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{date_text}--{entry_id}.md"

    def _write_original(self, path: Path, entry_id: str, entry_date: str, entry_type: str, status: str, raw_text: str) -> None:
        path.write_text(
            f"---\nid: {entry_id}\ndate: {entry_date}\ntype: {entry_type}\nstatus: {status}\ncontent: original\n---\n\n{raw_text.strip()}\n",
            encoding="utf-8",
        )

    def _write_clean(self, path: Path, entry: dict[str, Any], preview: dict[str, Any]) -> None:
        decision = preview.get("decision") if entry.get("entry_type") == "decision" else None
        theme_names = []
        for segment in preview.get("segments", []):
            for name in [segment["theme"], *(segment.get("tags") or [])]:
                if name not in theme_names:
                    theme_names.append(name)
        lines = [
            "---",
            f"id: {entry['id']}",
            f"date: {entry['entry_date']}",
            f"type: {entry['entry_type']}",
            "status: confirmed",
            *([f"decision_status: {decision['status']}"] if decision else []),
            *([f"review_date: {decision['timeline'].get('review_date') or ''}"] if decision else []),
            *([f"due_date: {decision['timeline'].get('due_date') or ''}"] if decision else []),
            *([f"archived_at: {decision.get('archived_at') or ''}"] if decision else []),
            "themes:",
            *[f"  - {name}" for name in theme_names],
            "---",
            "",
            f"# {entry['entry_date']}",
            "",
            preview["clean_text"],
            "",
            "## 主题片段",
            "",
        ]
        for segment in preview.get("segments", []):
            lines.extend([f"### {segment['theme']}", ""])
            if segment.get("tags"):
                lines.extend([f"Tags: {', '.join(segment['tags'])}", ""])
            lines.extend([segment["text"], ""])
        if decision:
            lines.extend(self._decision_markdown_lines(decision))
        if preview.get("goal_interpretations"):
            labels = {
                "progress": "进展",
                "blocker": "阻碍",
                "reflection": "反思",
                "related": "相关",
            }
            lines.extend(
                [
                    "## AI 目标解读（AI goal interpretation）",
                    "",
                    "以下内容由 AI 根据本条日记证据生成，并非用户原话或权威目标记录。",
                    "",
                ]
            )
            for item in preview["goal_interpretations"]:
                relation = labels.get(str(item["relation"]), str(item["relation"]))
                lines.extend(
                    [
                        f"### {item['goal_title']}",
                        "",
                        f"- 关系：{relation}",
                        f"- 日记证据：{item['evidence']}",
                        f"- AI 解读：{item['interpretation']}",
                        f"- AI 反馈：{item['feedback']}",
                        f"- 置信度：{item['confidence']:.2f}",
                        "",
                    ]
                )
        if preview.get("followups"):
            lines.extend(["## 反思问题", ""])
            lines.extend(f"- {item['question']}" for item in preview["followups"] if item.get("question"))
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    def _decision_markdown_lines(self, decision: dict[str, Any]) -> list[str]:
        lines = [
            "## Decision analysis",
            "",
            f"- Status: {decision['status']}",
            f"- Actual objective: {decision['objective']}",
            "",
            "### Options",
            "",
        ]
        for option in decision["options"]:
            suffix = " (do nothing)" if option.get("is_do_nothing") else ""
            lines.extend(
                [
                    f"#### {option['name']}{suffix}",
                    "",
                    f"- Facts: {self._inline_items(option.get('facts'))}",
                    f"- Assumptions: {self._inline_items(option.get('assumptions'))}",
                    f"- Reversible consequences: {self._inline_items(option.get('reversible_consequences'))}",
                    f"- Irreversible consequences: {self._inline_items(option.get('irreversible_consequences'))}",
                    "",
                ]
            )
        opportunity = decision["opportunity_cost"]
        lines.extend(
            [
                "### Opportunity cost",
                "",
                f"- Facts: {self._inline_items(opportunity.get('facts'))}",
                f"- Assumptions: {self._inline_items(opportunity.get('assumptions'))}",
                f"- Judgement: {opportunity.get('judgement', '')}",
                "",
                "### Likely regret",
                "",
                f"- In one year: {decision['likely_regret'].get('one_year', '') or 'Not specified'}",
                f"- In five years: {decision['likely_regret'].get('five_years', '') or 'Not specified'}",
                "",
                "### Assumptions that could be wrong",
                "",
            ]
        )
        assumptions = decision.get("assumptions") or []
        lines.extend([f"- {item}" for item in assumptions] or ["- None recorded."])
        experiment = decision["smallest_experiment"]
        lines.extend(
            [
                "",
                "### Smallest experiment that would reduce uncertainty",
                "",
                f"- Action: {experiment.get('action', '')}",
                f"- Uncertainty reduced: {experiment.get('uncertainty_reduced', '') or 'Not specified'}",
                f"- Timebox: {experiment.get('timebox', '') or 'Not specified'}",
                f"- Success signal: {experiment.get('success_signal', '') or 'Not specified'}",
                "",
                "### Recommendation",
                "",
                f"- Recommended option: {decision['recommendation']['option']}",
                f"- Facts: {self._inline_items(decision['recommendation'].get('facts'))}",
                f"- Assumptions: {self._inline_items(decision['recommendation'].get('assumptions'))}",
                f"- Judgement: {decision['recommendation'].get('judgement', '')}",
                "",
            ]
        )
        timeline = decision.get("timeline") or {}
        if timeline.get("review_date") or timeline.get("due_date") or timeline.get("notes"):
            lines.extend(
                [
                    "### Timeline",
                    "",
                    f"- Review date: {timeline.get('review_date') or 'Not specified'}",
                    f"- Due date: {timeline.get('due_date') or 'Not specified'}",
                    f"- Notes: {timeline.get('notes') or 'None'}",
                    "",
                ]
            )
        return lines

    @staticmethod
    def _inline_items(items: Any) -> str:
        values = [str(item) for item in (items or []) if str(item).strip()]
        return "; ".join(values) if values else "None recorded"
