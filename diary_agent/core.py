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
            for segment in preview.get("segments", []):
                theme_id = self._ensure_theme(db, segment["theme"])
                theme_names.append(segment["theme"])
                db.execute(
                    "INSERT INTO segments(id,entry_id,position,text,theme_id,theme_name) VALUES(?,?,?,?,?,?)",
                    (str(uuid.uuid4()), entry_id, segment["position"], segment["text"], theme_id, segment["theme"]),
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
            db.execute("UPDATE entries SET status='confirmed',confirmed_at=?,updated_at=? WHERE id=?", (confirmed_at, confirmed_at, entry_id))
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
        return {"period_start": start.isoformat(), "period_end": end.isoformat(), "has_content": bool(records), "entries": records}

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
        row = db.execute("SELECT id FROM themes WHERE normalized_name=?", (normalized,)).fetchone()
        if row:
            return str(row["id"])
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
