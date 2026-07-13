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


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    entry_type TEXT NOT NULL CHECK(entry_type IN ('diary','weekly','thought')),
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
    action TEXT NOT NULL CHECK(action IN ('create','activate','deactivate','rename','merge','split','reassign_segment')),
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
    scope TEXT NOT NULL CHECK(scope IN ('life','short_term','weekly')),
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
CREATE INDEX IF NOT EXISTS idx_theme_changes_status ON theme_change_proposals(status, created_at);
CREATE INDEX IF NOT EXISTS idx_goals_status_scope ON goals(status, scope, priority);
CREATE INDEX IF NOT EXISTS idx_goal_events_goal_created ON goal_events(goal_id, created_at);
CREATE INDEX IF NOT EXISTS idx_goal_links_goal_created ON goal_entry_links(goal_id, created_at);
CREATE INDEX IF NOT EXISTS idx_goal_changes_status ON goal_change_proposals(status, created_at);
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
        memory_files = {
            "user-preferences.md": "# User Preferences\n\n",
            "workflow-feedback.md": "# Workflow Feedback\n\n",
            "workflow-decisions.md": "# Workflow Decisions\n\n",
            "skill-change-history.md": "# Skill Change History\n\n",
            "goals.md": "# Goals\n\nNo confirmed goals.\n",
        }
        for name, content in memory_files.items():
            path = self.paths.memory / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        return {"root": str(self.paths.root), "database": str(self.paths.db)}

    def connect(self) -> sqlite3.Connection:
        self.paths.db.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.paths.db)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create_draft(self, raw_text: str, entry_type: str = "diary", source: str = "codex", entry_date: str | None = None) -> dict[str, Any]:
        self.initialize()
        if entry_type not in {"diary", "weekly", "thought"}:
            raise ValueError("entry_type must be diary, weekly, or thought")
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
        routing = self.route(text)
        context = self.retrieve_context(text)
        self.log_agent_run(entry_id, routing, sum(len(item["text"]) for item in context), 0)
        return {"entry_id": entry_id, "entry_date": date_text, "routing_decision": routing, "context": context}

    def route(self, text: str) -> dict[str, Any]:
        filler_count = len(FILLER_RE.findall(text))
        punctuation = sum(text.count(mark) for mark in "，。！？；,.!?;")
        speech_like = filler_count >= 1 or (len(text) > 120 and punctuation <= 1)
        multi_topic = len(MULTI_TOPIC_RE.findall(text)) >= 2 or text.count("\n") >= 3
        uncertain = bool(UNCERTAINTY_RE.search(text))
        continuity = bool(CONTINUITY_RE.search(text))
        return {
            "stages": {"clean": True, "classify": True, "continuity": True},
            "delegate": {
                "cleaner": speech_like or uncertain,
                "classifier": multi_topic,
                "continuity": continuity,
            },
            "signals": {
                "filler_count": filler_count,
                "speech_like": speech_like,
                "multi_topic": multi_topic,
                "uncertain_term": uncertain,
                "continuation_language": continuity,
            },
            "model_preference": {
                "cleaner": "lightweight_if_supported",
                "classifier": "lightweight_if_supported",
                "continuity": "capable",
                "orchestrator": "capable",
            },
        }

    def conservative_clean(self, text: str) -> str:
        cleaned = FILLER_RE.sub("", text)
        cleaned = re.sub(r"([，。！？；、])\1+", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r" *\n *", "\n", cleaned)
        return cleaned.strip(" ，")

    def retrieve_context(self, query: str, token_budget: int = 1800) -> list[dict[str, Any]]:
        """Return a relevance-driven context set with no fixed item-count cap."""
        self.initialize()
        char_budget = max(600, token_budget * 2)
        query_vec = _ngrams(query)
        terms = [term for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", query) if len(term) >= 2]
        candidates: dict[str, dict[str, Any]] = {}
        with self.connect() as db:
            rows: Iterable[sqlite3.Row]
            if terms:
                fts_query = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:12])
                try:
                    rows = db.execute(
                        "SELECT e.*, bm25(entries_fts) AS rank FROM entries_fts JOIN entries e ON e.id=entries_fts.entry_id WHERE entries_fts MATCH ? AND e.status='confirmed' ORDER BY rank",
                        (fts_query,),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            else:
                rows = []
            for row in rows:
                candidates[row["id"]] = dict(row)
            recent = db.execute("SELECT * FROM entries WHERE status='confirmed' ORDER BY entry_date DESC, confirmed_at DESC").fetchall()
            for row in recent:
                candidates.setdefault(row["id"], dict(row))

        scored = []
        for row in candidates.values():
            text = row.get("clean_text") or row.get("raw_text") or ""
            semantic = _cosine(query_vec, _ngrams(text))
            days = max(0, (_now().date() - datetime.fromisoformat(row["entry_date"]).date()).days)
            recency = 1 / (1 + days / 30)
            score = semantic * 0.82 + recency * 0.18
            if semantic > 0.04 or days <= 14:
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
            selected.append({"entry_id": row["id"], "date": row["entry_date"], "type": row["entry_type"], "score": round(score, 4), "text": snippet})
            used += len(snippet)
            covered.update(novelty_terms)
            previous_score = score
            if used >= char_budget:
                break
        return selected

    def save_preview(self, entry_id: str, clean_text: str, segments: list[dict[str, Any]], uncertainties: list[dict[str, Any]] | None = None, links: list[dict[str, Any]] | None = None, followups: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
            normalized_segments.append({"position": position, "text": text, "theme": theme})
        preview = {
            "clean_text": clean,
            "segments": normalized_segments,
            "uncertainties": uncertainties or [],
            "links": links or [],
            "followups": followups or [],
        }
        with self.connect() as db:
            current = db.execute("SELECT status FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not current:
                raise KeyError(entry_id)
            if current["status"] == "confirmed":
                raise ValueError("confirmed entries cannot be overwritten through preview")
            db.execute("UPDATE entries SET status='preview',clean_text=?,preview_json=?,updated_at=? WHERE id=?", (clean, _json(preview), _iso(), entry_id))
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
            db.execute("DELETE FROM segments WHERE entry_id=?", (entry_id,))
            theme_names = []
            stored_segments = []
            for segment in preview.get("segments", []):
                theme_id = self._ensure_theme(db, segment["theme"])
                theme = self._canonical_theme_row(db, theme_id)
                if not theme or theme["status"] != "active":
                    raise ValueError(f"theme is not active: {segment['theme']}")
                theme_name = str(theme["name"])
                theme_names.append(theme_name)
                stored_segments.append({**segment, "theme": theme_name})
                db.execute(
                    "INSERT INTO segments(id,entry_id,position,text,theme_id,theme_name) VALUES(?,?,?,?,?,?)",
                    (str(uuid.uuid4()), entry_id, segment["position"], segment["text"], theme["id"], theme_name),
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
            preview = {**preview, "segments": stored_segments}
            confirmed_at = _iso()
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
                "SELECT id,entry_date,clean_text,preview_json FROM entries WHERE status='confirmed' AND entry_type!='weekly' AND entry_date BETWEEN ? AND ? ORDER BY entry_date,created_at",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            records = []
            for row in rows:
                preview = json.loads(row["preview_json"] or "{}")
                records.append({"entry_id": row["id"], "date": row["entry_date"], "clean_text": row["clean_text"], "segments": preview.get("segments", [])})
            goals = self._weekly_goal_context(db, start.isoformat(), end.isoformat())
        return {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "has_content": bool(records),
            "entries": records,
            "goals": goals,
            "theme_review": self.theme_review_context(moment),
        }

    def theme_review_context(self, now: datetime | None = None) -> dict[str, Any]:
        self.initialize()
        moment = (now or _now()).astimezone(TZ)
        recent_start = (moment.date() - timedelta(days=90)).isoformat()
        with self.connect() as db:
            rows = db.execute(
                """SELECT t.*, COUNT(s.id) AS total_uses,
                   SUM(CASE WHEN e.entry_date>=? THEN 1 ELSE 0 END) AS recent_uses
                   FROM themes t
                   LEFT JOIN segments s ON s.theme_id=t.id
                   LEFT JOIN entries e ON e.id=s.entry_id AND e.status='confirmed'
                   GROUP BY t.id ORDER BY t.status, total_uses DESC, t.name""",
                (recent_start,),
            ).fetchall()
            themes: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                representatives = db.execute(
                    """SELECT s.id AS segment_id,s.entry_id,e.entry_date,s.text
                       FROM segments s JOIN entries e ON e.id=s.entry_id
                       WHERE s.theme_id=? AND e.status='confirmed'
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
        allowed = {"create", "activate", "deactivate", "rename", "merge", "split", "reassign_segment"}
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
                if action not in {"create", "reassign_segment"} and not source:
                    raise ValueError(f"{action} requires source_theme_id")
                if action == "merge" and not target:
                    raise ValueError("merge requires target_theme_id")
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
            db.execute("UPDATE segments SET theme_id=?,theme_name=? WHERE id=?", (target["id"], target["name"], segment_id))
            self._refresh_entry_fts(db, {str(segment["entry_id"])})
            return {"segment_id": segment_id, "theme_ids": [target["id"]]}
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

    def _refresh_entry_fts(self, db: sqlite3.Connection, entry_ids: Iterable[str]) -> None:
        for entry_id in set(entry_ids):
            entry = db.execute("SELECT clean_text,status FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not entry or entry["status"] != "confirmed":
                continue
            names = []
            for segment in db.execute("SELECT theme_id FROM segments WHERE entry_id=? ORDER BY position", (entry_id,)).fetchall():
                if not segment["theme_id"]:
                    continue
                theme = self._canonical_theme_row(db, str(segment["theme_id"]))
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
            if scope not in {"life", "short_term", "weekly"} or not title:
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
        if scope not in {"life", "short_term", "weekly"}:
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
        rank = {"life": 0, "short_term": 1, "weekly": 2}
        if rank[str(parent["scope"])] >= rank[scope]:
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
            events = db.execute("SELECT event_type,payload_json,evidence_json,created_at FROM goal_events WHERE goal_id=? AND substr(created_at,1,10) BETWEEN ? AND ? ORDER BY created_at", (row["id"], start, end)).fetchall()
            item["weekly_evidence"] = [dict(value) for value in evidence]
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
        labels = {"life": "Life", "short_term": "Short-term", "weekly": "Weekly"}
        for scope in ("life", "short_term", "weekly"):
            lines.extend([f"## {labels[scope]}", ""])
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
        return {"revision_id": revision_id, "status": "proposed", "snapshot_commit": commit, "metadata_commit": metadata_commit, "proposal_path": str(proposal_path)}

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
        if status in {"applied", "failed", "rejected"}:
            commit = self.git_snapshot(f"chore(diary): {status} skill revision {revision_id[:8]}")
            with self.connect() as db:
                db.execute("UPDATE skill_revisions SET git_after_commit=?,updated_at=? WHERE id=?", (commit, _iso(), revision_id))
                db.commit()
            self.git_snapshot(f"chore(diary): record revision result {revision_id[:8]}")
        return {"revision_id": revision_id, "status": status, "commit": commit}

    def search(self, query: str, token_budget: int = 1800) -> list[dict[str, Any]]:
        return self.retrieve_context(query, token_budget=token_budget)

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
        theme_names = [segment["theme"] for segment in preview.get("segments", [])]
        lines = [
            "---",
            f"id: {entry['id']}",
            f"date: {entry['entry_date']}",
            f"type: {entry['entry_type']}",
            "status: confirmed",
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
            lines.extend([f"### {segment['theme']}", "", segment["text"], ""])
        if preview.get("followups"):
            lines.extend(["## 反思问题", ""])
            lines.extend(f"- {item['question']}" for item in preview["followups"] if item.get("question"))
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
