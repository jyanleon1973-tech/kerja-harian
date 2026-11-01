"""SQLite によるジョブ・段階出力・手動修正・書き出しの管理。
Postgres（Supabase 等）へ移す場合はこのモジュールだけ差し替える。"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,            -- queued | running | done | failed | canceled
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  started_at REAL,
  finished_at REAL,
  progress REAL NOT NULL DEFAULT 0,
  stage TEXT,
  message TEXT,
  params_json TEXT NOT NULL,
  video_key TEXT NOT NULL,
  video_meta_json TEXT,
  result_key TEXT,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  model_versions_json TEXT,
  pipeline_version TEXT
);
CREATE TABLE IF NOT EXISTS stage_outputs (
  job_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  stage TEXT NOT NULL,
  key TEXT NOT NULL,
  duration_ms REAL NOT NULL,
  created_at REAL NOT NULL,
  summary_json TEXT,
  PRIMARY KEY (job_id, seq)
);
CREATE TABLE IF NOT EXISTS corrections (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  payload_json TEXT NOT NULL,
  training_consent INTEGER NOT NULL DEFAULT 0,
  author TEXT
);
CREATE TABLE IF NOT EXISTS exports (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  params_json TEXT NOT NULL,
  key TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_corrections_job ON corrections(job_id, created_at);
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA foreign_keys=ON")
            with self._lock:
                yield con
                con.commit()
        finally:
            con.close()

    # ---- jobs ----
    def create_job(self, video_key: str, params: dict[str, Any], pipeline_version: str) -> dict[str, Any]:
        jid = new_id("job")
        now = time.time()
        with self.connect() as con:
            con.execute(
                "INSERT INTO jobs(id,status,created_at,updated_at,progress,params_json,video_key,pipeline_version) VALUES(?,?,?,?,?,?,?,?)",
                (jid, "queued", now, now, 0.0, json.dumps(params, ensure_ascii=False), video_key, pipeline_version),
            )
        return self.get_job(jid)

    def get_job(self, jid: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        return self._job_row(row) if row else None

    def update_job(self, jid: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        for k in ("params", "video_meta", "model_versions"):
            if k in fields:
                fields[k + "_json"] = json.dumps(fields.pop(k), ensure_ascii=False)
        cols = ", ".join(f"{k}=?" for k in fields)
        with self.connect() as con:
            con.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), jid))

    def claim_next_job(self) -> dict[str, Any] | None:
        """queued のジョブを 1 件 running にして返す（単一ワーカー向けの簡易キュー）。"""
        with self.connect() as con:
            row = con.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            now = time.time()
            con.execute("UPDATE jobs SET status='running', started_at=?, updated_at=?, attempts=attempts+1 WHERE id=? AND status='queued'", (now, now, row["id"]))
        return self.get_job(row["id"])

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._job_row(r) for r in rows]

    def running_count(self) -> int:
        with self.connect() as con:
            return con.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]

    def old_jobs(self, older_than: float) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM jobs WHERE created_at<? ", (older_than,)).fetchall()
        return [self._job_row(r) for r in rows]

    def delete_job(self, jid: str) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM stage_outputs WHERE job_id=?", (jid,))
            con.execute("DELETE FROM corrections WHERE job_id=?", (jid,))
            con.execute("DELETE FROM exports WHERE job_id=?", (jid,))
            con.execute("DELETE FROM jobs WHERE id=?", (jid,))

    @staticmethod
    def _job_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for k in ("params", "video_meta", "model_versions"):
            raw = d.pop(k + "_json", None)
            d[k] = json.loads(raw) if raw else None
        return d

    # ---- stage outputs ----
    def add_stage_output(self, job_id: str, seq: int, stage: str, key: str, duration_ms: float, summary: dict[str, Any] | None) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO stage_outputs(job_id,seq,stage,key,duration_ms,created_at,summary_json) VALUES(?,?,?,?,?,?,?)",
                (job_id, seq, stage, key, duration_ms, time.time(), json.dumps(summary or {}, ensure_ascii=False)),
            )

    def stage_outputs(self, job_id: str) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM stage_outputs WHERE job_id=? ORDER BY seq", (job_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["summary"] = json.loads(d.pop("summary_json") or "{}")
            out.append(d)
        return out

    # ---- corrections ----
    def add_correction(self, job_id: str, payload: dict[str, Any], training_consent: bool, author: str | None) -> dict[str, Any]:
        cid = new_id("cor")
        with self.connect() as con:
            con.execute(
                "INSERT INTO corrections(id,job_id,created_at,payload_json,training_consent,author) VALUES(?,?,?,?,?,?)",
                (cid, job_id, time.time(), json.dumps(payload, ensure_ascii=False), 1 if training_consent else 0, author),
            )
        return {"id": cid, "job_id": job_id, "training_consent": training_consent}

    def corrections(self, job_id: str) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM corrections WHERE job_id=? ORDER BY created_at", (job_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d.pop("payload_json"))
            d["training_consent"] = bool(d["training_consent"])
            out.append(d)
        return out

    # ---- exports ----
    def create_export(self, job_id: str, params: dict[str, Any]) -> dict[str, Any]:
        eid = new_id("exp")
        now = time.time()
        with self.connect() as con:
            con.execute("INSERT INTO exports(id,job_id,status,created_at,updated_at,params_json) VALUES(?,?,?,?,?,?)", (eid, job_id, "queued", now, now, json.dumps(params)))
        return self.get_export(eid)

    def update_export(self, eid: str, **fields: Any) -> None:
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self.connect() as con:
            con.execute(f"UPDATE exports SET {cols} WHERE id=?", (*fields.values(), eid))

    def get_export(self, eid: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM exports WHERE id=?", (eid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["params"] = json.loads(d.pop("params_json"))
        return d
