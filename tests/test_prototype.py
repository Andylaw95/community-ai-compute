import concurrent.futures
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from prototype.compute import result_for
from prototype.engine import Coordinator, Problem
from prototype.server import make_server


def eventually(predicate, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(0.025)
    raise AssertionError("condition did not become true")


class Running:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.core = Coordinator(Path(self.temp.name) / "demo.sqlite")
        self.server, self.supervisor = make_server(self.core, 0)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        for node in self.core.nodes:
            self.supervisor.start(node)
        eventually(lambda: all(n["heartbeat"] > 0 for n in self.core.nodes.values()))
        return self

    def request(self, path, data=None, headers=None):
        body = None if data is None else json.dumps(data).encode()
        req = Request(self.base + path, body, {"Content-Type": "application/json", **(headers or {})})
        try:
            with urlopen(req, timeout=5) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)

    def enable(self):
        self.request("/api/policy", {"consent": True, "mode": "manual", "budget": 60})

    def job(self, key="test", count=96, batch=16):
        status, data = self.request("/api/jobs", {"count": count, "batch": batch, "seed": 7}, {"Idempotency-Key": key})
        assert status == 201, data
        return data["job_id"]

    def done(self, jid):
        return eventually(lambda: (j if (j := self.request(f"/api/jobs/{jid}")[1])["status"] == "completed" else None))

    def __exit__(self, *args):
        self.supervisor.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.core.close()
        self.temp.cleanup()


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.c = Coordinator(":memory:", clock=lambda: self.now)
        for n in self.c.nodes.values():
            n["alive"] = True
        self.c.set_policy({"consent": True, "mode": "manual", "budget": 30})

    def tearDown(self):
        self.c.close()

    def job(self, key="j", count=8):
        return self.c.submit({"count": count, "batch": 4, "seed": 1}, key)["job_id"]

    def payload(self, lease):
        return {"attempt_id": lease["attempt_id"], "compute_ms": 1,
                "results": result_for(lease["seed"], lease["start"], lease["stop"])}

    def test_idempotent_submission_and_conflict(self):
        jid = self.job()
        self.assertEqual(jid, self.job())
        self.assertEqual(len(self.c.snapshot()["jobs"]), 1)
        with self.assertRaises(Problem) as caught:
            self.job(count=9)
        self.assertEqual(caught.exception.status, 409)

    def test_exact_results_and_atomic_credit(self):
        jid = self.job()
        for node in ("cpu-1", "cpu-2"):
            lease = self.c.claim(node)["lease"]
            self.assertEqual(self.c.accept(node, self.payload(lease))["credits_awarded"], 4)
        self.assertEqual(self.c.results(jid)["results"], result_for(1, 0, 8))
        self.assertEqual(self.c.snapshot()["totals"]["credits"], 8)

    def test_concurrent_reward_replay(self):
        self.job(count=4)
        payload = self.payload(self.c.claim("cpu-1")["lease"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: self.c.accept("cpu-1", payload), range(16)))
        self.assertEqual(sum(x["credits_awarded"] for x in replies), 4)
        self.assertEqual(self.c.snapshot()["totals"]["accepted"], 1)

    def test_invalid_result_requeues_without_credit(self):
        self.job(count=4)
        bad = self.payload(self.c.claim("cpu-1")["lease"])
        bad["results"][0]["sum"] += 1
        self.assertEqual(self.c.accept("cpu-1", bad)["status"], "invalid")
        self.assertEqual(self.c.snapshot()["totals"]["credits"], 0)
        good = self.payload(self.c.claim("cpu-2")["lease"])
        self.assertEqual(self.c.accept("cpu-2", good)["credits_awarded"], 4)

    def test_expired_lease_rejects_late_result(self):
        self.job(count=4)
        old = self.payload(self.c.claim("cpu-1")["lease"])
        self.now += 3
        fresh = self.payload(self.c.claim("cpu-2")["lease"])
        self.assertEqual(self.c.accept("cpu-1", old)["status"], "stale")
        self.c.accept("cpu-2", fresh)
        self.assertEqual(self.c.snapshot()["totals"]["credits"], 4)

    def test_failure_retry_limit(self):
        self.job(count=4)
        for _ in range(3):
            a = self.c.claim("cpu-1")["lease"]
            self.c.accept("cpu-1", {"attempt_id": a["attempt_id"], "results": []})
        self.assertIsNone(self.c.claim("cpu-1")["lease"])
        self.assertEqual(self.c.snapshot()["jobs"][0]["status"], "failed")

    def test_consent_pause_and_foreground_policy(self):
        self.job()
        for change in ({"consent": False}, {"consent": True, "paused": True},
                       {"paused": False, "foreground_busy": True, "usage": "idle"}):
            self.c.set_policy(change)
            self.assertIsNone(self.c.claim("cpu-1")["lease"])
        self.c.set_policy({"usage": "coexist", "budget": 80})
        self.assertEqual(self.c.limits()["effective_budget"], 15)
        self.c.set_policy({"mode": "auto"})
        self.assertLessEqual(self.c.limits()["effective_budget"], 15)

    def test_pause_releases_do_not_exhaust_fault_limit(self):
        self.job(count=4)
        for _ in range(5):
            a = self.c.claim("cpu-1")["lease"]
            self.c.release("cpu-1", a["attempt_id"])
        self.assertEqual(self.c.snapshot()["jobs"][0]["chunks"][0]["tries"], 0)

    def test_malformed_and_bounded_input(self):
        for data in ({"count": True}, {"count": 4097}, {"count": 1, "batch": 0},
                     {"count": 1, "command": "anything"}, {"count": 1, "title": "x" * 81}):
            with self.assertRaises(Problem):
                self.c.submit(data, "bad")
        with self.assertRaises(Problem):
            self.c._node([])
        with self.assertRaises(Problem):
            self.c.set_policy({"consent": "yes"})

    def test_restart_preserves_ledger_and_revokes_leases(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "db.sqlite"
            c = Coordinator(path)
            c.nodes["cpu-1"]["alive"] = True
            c.set_policy({"consent": True, "mode": "manual"})
            c.submit({"count": 8, "batch": 4}, "persist")
            lease = c.claim("cpu-1")["lease"]
            c.accept("cpu-1", self.payload(lease))
            old = c.claim("cpu-1")["lease"]
            c.close()
            reopened = Coordinator(path)
            try:
                self.assertEqual(reopened.snapshot()["totals"]["credits"], 4)
                self.assertFalse(reopened.policy["consent"])
                self.assertEqual(reopened.accept("cpu-1", self.payload(old))["status"], "stale")
            finally:
                reopened.close()


class IntegrationTests(unittest.TestCase):
    evidence = {}

    def test_three_real_processes_and_delivery(self):
        with Running() as r:
            r.enable()
            job = r.job(count=384, batch=16)
            r.done(job)
            status, output = r.request(f"/api/jobs/{job}/results")
            self.assertEqual(status, 200)
            self.assertEqual(len(output["results"]), 384)
            rows = r.core.db.execute("SELECT DISTINCT node FROM ledger").fetchall()
            self.assertEqual(len(rows), 3)
            pids = [n["pid"] for n in r.core.nodes.values()]
            self.assertEqual(len(set(pids)), 3)
            self.evidence["real_workers"] = {"pids": pids, "accepted_images": 384, "nodes_used": 3}
        self.assertTrue(all(p.poll() is not None for p in r.supervisor.processes.values()))

    def test_actual_process_dropout_retried(self):
        with Running() as r:
            for node in ("cpu-2", "cpu-3"):
                r.supervisor.stop(node)
            r.request("/api/demo/fault", {"node": "cpu-1", "mode": "exit"})
            r.enable()
            start = time.perf_counter()
            job = r.job(count=64, batch=16)
            eventually(lambda: r.supervisor.processes["cpu-1"].poll() is not None)
            r.supervisor.start("cpu-2")
            r.done(job)
            s = r.core.snapshot()
            self.assertEqual(s["totals"]["attempts"].get("expired"), 1)
            self.assertEqual(s["totals"]["credits"], 64)
            self.evidence["dropout"] = {"wall_seconds": time.perf_counter() - start,
                "lease_seconds": 2, "expired_attempts": 1, "credits": 64,
                "exit_code": r.supervisor.processes["cpu-1"].returncode}

    def test_fault_validation_and_replay(self):
        with Running() as r:
            for node in ("cpu-2", "cpu-3"):
                r.supervisor.stop(node)
            r.enable()
            for key, mode in (("bad", "invalid"), ("replay", "replay")):
                r.request("/api/demo/fault", {"node": "cpu-1", "mode": mode})
                r.done(r.job(key=key, count=32, batch=16))
            s = r.core.snapshot()
            self.assertEqual(s["totals"]["credits"], 64)
            self.assertEqual(s["totals"]["attempts"].get("invalid"), 1)
            self.assertTrue(any(e["kind"] == "duplicate" for e in s["events"]))
            self.evidence["invalid_and_replay"] = s["totals"]

    def test_api_boundary_and_submission_replay(self):
        with Running() as r:
            self.assertEqual(r.request("/api/policy", {}, {"Origin": "https://attacker.invalid"})[0], 403)
            self.assertEqual(r.request("/api/state", headers={"Host": "attacker.invalid"})[0], 403)
            self.assertEqual(r.request("/internal/claim", {"node": "cpu-1"})[0], 403)
            self.assertEqual(r.request("/api/jobs", {"count": 4097}, {"Idempotency-Key": "large"})[0], 400)
            self.assertEqual(r.request("/api/demo/fault", {"node": [], "mode": "exit"})[0], 400)
            self.assertEqual(r.request("/api/jobs", {"title": "x" * 5000})[0], 413)
            status, j = r.request("/api/jobs", {"count": 16}, {"Idempotency-Key": "once"})
            self.assertEqual(status, 201)
            repeat = r.request("/api/jobs", {"count": 16}, {"Idempotency-Key": "once"})
            self.assertEqual(repeat[1]["job_id"], j["job_id"])
            self.assertTrue(repeat[1]["duplicate"])
            self.assertEqual(r.request("/api/jobs", {"count": 17}, {"Idempotency-Key": "once"})[0], 409)

    def test_live_resource_policy_pauses_and_resumes(self):
        with Running() as r:
            job = r.job(count=256, batch=16)
            time.sleep(.2)
            self.assertEqual(r.core.snapshot()["totals"]["credits"], 0)
            r.request("/api/policy", {"consent": True, "mode": "manual", "foreground_busy": True})
            time.sleep(.2)
            self.assertEqual(r.core.snapshot()["totals"]["credits"], 0)
            r.request("/api/policy", {"foreground_busy": False, "paused": True})
            time.sleep(.2)
            self.assertEqual(r.core.snapshot()["totals"]["credits"], 0)
            r.request("/api/policy", {"paused": False, "budget": 20})
            r.done(job)
            self.assertEqual(r.core.snapshot()["totals"]["credits"], 256)


if __name__ == "__main__":
    unittest.main(verbosity=2)
