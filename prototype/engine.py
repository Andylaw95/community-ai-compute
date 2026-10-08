"""SQLite coordinator. Fixed workload, leases, exact recheck, atomic demo-credit ledger."""
import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import threading
import time
import uuid

from .compute import WORKLOAD, SIDE, result_for


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise Problem(400, f"{name} 必須是 {low}–{high} 的整數")
    return value


def fields(data, allowed):
    if not isinstance(data, dict) or set(data) - set(allowed):
        raise Problem(400, "不支援的欄位或 JSON 格式")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Coordinator:
    def __init__(self, path, clock=time.time, lease_seconds=2.0):
        self.clock, self.lease_seconds = clock, lease_seconds
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
          title TEXT NOT NULL, count INTEGER NOT NULL, batch INTEGER NOT NULL, seed INTEGER NOT NULL,
          created REAL NOT NULL, completed REAL);
        CREATE TABLE IF NOT EXISTS chunks (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), first_i INTEGER NOT NULL,
          last_i INTEGER NOT NULL, state TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0,
          result TEXT, accepted_attempt TEXT, verify_ms REAL NOT NULL DEFAULT 0,
          UNIQUE(job_id, first_i));
        CREATE TABLE IF NOT EXISTS attempts (
          id TEXT PRIMARY KEY, chunk_id TEXT NOT NULL REFERENCES chunks(id), node TEXT NOT NULL,
          state TEXT NOT NULL, deadline REAL NOT NULL, started REAL NOT NULL,
          finished REAL, compute_ms REAL NOT NULL DEFAULT 0, verify_ms REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS ledger (
          id INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE NOT NULL REFERENCES chunks(id),
          job_id TEXT NOT NULL REFERENCES jobs(id), attempt_id TEXT UNIQUE NOT NULL,
          node TEXT NOT NULL, credits INTEGER NOT NULL CHECK(credits > 0), created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, created REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
        """)
        self.policy = {"consent": False, "paused": False, "budget": 30,
                       "mode": "auto", "usage": "idle", "foreground_busy": False}
        self.nodes = {f"cpu-{i}": {"pid": None, "alive": False, "heartbeat": 0, "fault": None}
                      for i in range(1, 4)}
        with self.lock, self.db:
            for row in self.db.execute("SELECT * FROM attempts WHERE state='leased'").fetchall():
                self._requeue(row, "restart")

    def close(self):
        self.db.close()

    def event(self, kind, detail):
        self.db.execute("INSERT INTO events(created,kind,detail) VALUES(?,?,?)",
                        (self.clock(), kind, str(detail)[:200]))
        self.db.execute("DELETE FROM events WHERE id <= (SELECT COALESCE(MAX(id),0)-500 FROM events)")

    def limits(self):
        p = self.policy
        try:
            load = os.getloadavg()[0]
        except OSError:
            load = None
        ratio = min(1.0, load / (os.cpu_count() or 1)) if load is not None else 1.0
        q = p["budget"]
        if p["mode"] == "auto":
            q = min(q, max(5, int(q * (1 - ratio)))) if load is not None else 0
        if not p["consent"] or p["paused"] or (p["usage"] == "idle" and p["foreground_busy"]):
            q = 0
        elif p["usage"] == "coexist" and p["foreground_busy"]:
            q = min(q, 15)
        return {**p, "effective_budget": q, "load_1m": load,
                "budget_unit": "per-worker cooperative duty cycle, not CPU/GPU isolation"}

    def set_policy(self, data):
        fields(data, self.policy)
        new = {**self.policy, **data}
        for name in ("consent", "paused", "foreground_busy"):
            if type(new[name]) is not bool:
                raise Problem(400, f"{name} 必須是布林值")
        integer(new["budget"], "budget", 5, 80)
        if new["mode"] not in ("auto", "manual") or new["usage"] not in ("idle", "coexist"):
            raise Problem(400, "不支援的資源模式")
        with self.lock, self.db:
            self.policy = new
            self.event("policy", canonical(new))
            return self.limits()

    def submit(self, data, request_key):
        fields(data, ("title", "count", "batch", "seed"))
        if not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_key):
            raise Problem(400, "需要 1–80 字元的 Idempotency-Key（英數、_、-）")
        count = integer(data.get("count"), "count", 1, 4096)
        batch = integer(data.get("batch", 32), "batch", 4, 128)
        seed = integer(data.get("seed", 7), "seed", 0, 1000000)
        title = data.get("title", "合成影像亮度統計")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
            raise Problem(400, "title 必須是 1–80 個字元")
        payload = {"title": title.strip(), "count": count, "batch": batch, "seed": seed}
        digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
        with self.lock, self.db:
            old = self.db.execute("SELECT * FROM jobs WHERE request_key=?", (request_key,)).fetchone()
            if old:
                if old["request_hash"] != digest:
                    raise Problem(409, "相同冪等鍵不能提交不同內容")
                return {"job_id": old["id"], "duplicate": True}
            if self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] >= 25:
                raise Problem(429, "本機示範最多保留 25 份工作；請以新的資料庫開始另一輪")
            jid = "job_" + uuid.uuid4().hex[:12]
            self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,NULL)",
                            (jid, request_key, digest, title.strip(), count, batch, seed, self.clock()))
            for start in range(0, count, batch):
                self.db.execute("INSERT INTO chunks(id,job_id,first_i,last_i,state) VALUES(?,?,?,?,?)",
                                (f"{jid}_{start}", jid, start, min(count, start + batch), "queued"))
            self.event("submitted", jid)
            return {"job_id": jid, "duplicate": False}

    def _node(self, node):
        if not isinstance(node, str) or node not in self.nodes:
            raise Problem(400, "未知工作程序")

    def _requeue(self, attempt, reason):
        self.db.execute("UPDATE attempts SET state=?,finished=? WHERE id=?",
                        (reason, self.clock(), attempt["id"]))
        chunk = self.db.execute("SELECT tries FROM chunks WHERE id=?", (attempt["chunk_id"],)).fetchone()
        # A voluntary pause relinquishes a lease without exhausting fault retries.
        tries = max(0, chunk["tries"] - 1) if reason == "released" else chunk["tries"]
        state = "failed" if tries >= 3 else "queued"
        self.db.execute("UPDATE chunks SET state=?,tries=? WHERE id=?",
                        (state, tries, attempt["chunk_id"]))
        self.event(reason, attempt["id"])

    def expire(self):
        for a in self.db.execute("SELECT * FROM attempts WHERE state='leased' AND deadline<=?",
                                 (self.clock(),)).fetchall():
            self._requeue(a, "expired")

    def claim(self, node):
        self._node(node)
        with self.lock, self.db:
            self.expire()
            self.nodes[node]["heartbeat"] = self.clock()
            policy = self.limits()
            if not self.nodes[node]["alive"] or not policy["effective_budget"]:
                return {"lease": None, "policy": policy}
            if self.db.execute("SELECT 1 FROM attempts WHERE node=? AND state='leased'", (node,)).fetchone():
                raise Problem(409, "程序已有租約")
            chunk = self.db.execute("""SELECT c.*,j.seed FROM chunks c JOIN jobs j ON j.id=c.job_id
                WHERE c.state='queued' ORDER BY j.created,c.tries,c.first_i LIMIT 1""").fetchone()
            if not chunk:
                return {"lease": None, "policy": policy}
            aid = "attempt_" + uuid.uuid4().hex
            now = self.clock()
            self.db.execute("INSERT INTO attempts(id,chunk_id,node,state,deadline,started) VALUES(?,?,?,?,?,?)",
                            (aid, chunk["id"], node, "leased", now + self.lease_seconds, now))
            self.db.execute("UPDATE chunks SET state='leased',tries=tries+1 WHERE id=?", (chunk["id"],))
            fault = self.nodes[node]["fault"]
            self.nodes[node]["fault"] = None
            self.event("leased", f"{node}: {chunk['id']}")
            return {"lease": {"attempt_id": aid, "chunk_id": chunk["id"], "job_id": chunk["job_id"],
                              "start": chunk["first_i"], "stop": chunk["last_i"], "seed": chunk["seed"],
                              "workload": WORKLOAD, "fault": fault}, "policy": policy}

    def heartbeat(self, node, attempt_id):
        self._node(node)
        with self.lock, self.db:
            self.expire()
            self.nodes[node]["heartbeat"] = self.clock()
            a = self.db.execute("SELECT * FROM attempts WHERE id=? AND node=?", (attempt_id, node)).fetchone()
            valid = bool(a and a["state"] == "leased")
            if valid:
                self.db.execute("UPDATE attempts SET deadline=? WHERE id=?",
                                (self.clock() + self.lease_seconds, attempt_id))
            return {"valid": valid, "policy": self.limits()}

    def release(self, node, attempt_id):
        self._node(node)
        with self.lock, self.db:
            a = self.db.execute("SELECT * FROM attempts WHERE id=? AND node=?", (attempt_id, node)).fetchone()
            if a and a["state"] == "leased":
                self._requeue(a, "released")
            return {"released": True}

    def accept(self, node, data):
        fields(data, ("attempt_id", "results", "compute_ms"))
        self._node(node)
        aid = data.get("attempt_id")
        if not isinstance(aid, str) or len(aid) > 80:
            raise Problem(400, "invalid attempt_id")
        duration = data.get("compute_ms", 0)
        if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= duration <= 60000:
            raise Problem(400, "invalid compute_ms")
        with self.lock, self.db:
            self.expire()
            a = self.db.execute("SELECT * FROM attempts WHERE id=? AND node=?", (aid, node)).fetchone()
            if a and a["state"] == "accepted":
                self.event("duplicate", aid)
                return {"status": "duplicate", "credits_awarded": 0}
            if not a or a["state"] != "leased":
                return {"status": "stale", "credits_awarded": 0}
            c = self.db.execute("SELECT c.*,j.seed FROM chunks c JOIN jobs j ON c.job_id=j.id WHERE c.id=?",
                                (a["chunk_id"],)).fetchone()
            start = time.perf_counter()
            expected = result_for(c["seed"], c["first_i"], c["last_i"])
            verify_ms = (time.perf_counter() - start) * 1000
            self.db.execute("UPDATE attempts SET compute_ms=?,verify_ms=? WHERE id=?", (duration, verify_ms, aid))
            # Canonical serialization avoids Python's True == 1 / float == int equivalence.
            if canonical(data.get("results")) != canonical(expected):
                self._requeue(a, "invalid")
                return {"status": "invalid", "credits_awarded": 0}
            self.db.execute("UPDATE attempts SET state='accepted',finished=? WHERE id=?", (self.clock(), aid))
            self.db.execute("UPDATE chunks SET state='accepted',result=?,accepted_attempt=?,verify_ms=? WHERE id=?",
                            (canonical(expected), aid, verify_ms, c["id"]))
            credits = c["last_i"] - c["first_i"]
            self.db.execute("INSERT INTO ledger(chunk_id,job_id,attempt_id,node,credits,created) VALUES(?,?,?,?,?,?)",
                            (c["id"], c["job_id"], aid, node, credits, self.clock()))
            if not self.db.execute("SELECT 1 FROM chunks WHERE job_id=? AND state!='accepted'", (c["job_id"],)).fetchone():
                self.db.execute("UPDATE jobs SET completed=? WHERE id=?", (self.clock(), c["job_id"]))
            self.event("accepted", f"{c['id']} +{credits} demo credits")
            return {"status": "accepted", "credits_awarded": credits, "verify_ms": verify_ms}

    def results(self, jid):
        with self.lock:
            job = self.db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            if not job:
                raise Problem(404, "找不到工作")
            if job["completed"] is None:
                raise Problem(409, "工作未全部驗證完成")
            out = []
            for c in self.db.execute("SELECT result FROM chunks WHERE job_id=? ORDER BY first_i", (jid,)):
                out.extend(json.loads(c["result"]))
            return {"job_id": jid, "workload": WORKLOAD, "image_size": [SIDE, SIDE], "results": out}

    def snapshot(self):
        with self.lock, self.db:
            self.expire()
            jobs = []
            for j in self.db.execute("SELECT * FROM jobs ORDER BY created DESC"):
                chunks = [dict(c) for c in self.db.execute(
                    "SELECT id,state,tries,first_i,last_i,accepted_attempt FROM chunks WHERE job_id=? ORDER BY first_i", (j["id"],))]
                states = {s: sum(c["state"] == s for c in chunks) for s in ("queued", "leased", "accepted", "failed")}
                state = "completed" if j["completed"] else "failed" if states["failed"] else "running" if states["leased"] else "queued"
                jobs.append({**{k: j[k] for k in ("id", "title", "count", "batch", "seed", "created", "completed")},
                             "status": state, "chunks": chunks, "phases": states})
            nodes = []
            for name, n in self.nodes.items():
                current = self.db.execute("SELECT chunk_id FROM attempts WHERE node=? AND state='leased'", (name,)).fetchone()
                accepted = self.db.execute("SELECT COUNT(*) FROM ledger WHERE node=?", (name,)).fetchone()[0]
                state = "stopped" if not n["alive"] else "working" if current else "ready" if self.limits()["effective_budget"] else "paused"
                nodes.append({"id": name, **n, "status": state, "current": current[0] if current else None, "accepted": accepted})
            totals = dict(self.db.execute("SELECT COUNT(*) accepted,COALESCE(SUM(credits),0) credits FROM ledger").fetchone())
            timings = dict(self.db.execute("SELECT COALESCE(SUM(compute_ms),0) compute_ms,COALESCE(SUM(verify_ms),0) verify_ms FROM attempts").fetchone())
            counts = {row[0]: row[1] for row in self.db.execute("SELECT state,COUNT(*) FROM attempts GROUP BY state")}
            ledger = [dict(r) for r in self.db.execute("SELECT * FROM ledger ORDER BY id DESC LIMIT 20")]
            events = [dict(r) for r in self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 35")]
            return {"jobs": jobs, "nodes": nodes, "policy": self.limits(), "totals": {**totals, **timings, "attempts": counts},
                    "ledger": ledger, "events": events, "hardware": {"system": platform.system(), "machine": platform.machine(),
                    "logical_cpus": os.cpu_count(), "gpu": "not detected or used", "image_side": SIDE},
                    "workload": WORKLOAD, "demo_only": True}
