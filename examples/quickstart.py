"""Explicitly opt in to a temporary synthetic CPU demo, then stop all workers.

Three processes run on this computer. No remote machines or AI models are used.
"""
import json
from pathlib import Path
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from prototype.engine import Coordinator
from prototype.server import make_server


def run():
    with tempfile.TemporaryDirectory(prefix="community-compute-") as directory:
        core = Coordinator(Path(directory) / "demo.sqlite")
        server = supervisor = thread = None
        summary = None
        try:
            server, supervisor = make_server(core, 0)
            base = f"http://127.0.0.1:{server.server_port}"
            opener = build_opener(ProxyHandler({}))

            def request(path, data=None, key=None):
                headers = {"Content-Type": "application/json"}
                if key:
                    headers["Idempotency-Key"] = key
                body = None if data is None else json.dumps(data).encode()
                req = Request(base + path, body, headers)
                try:
                    with opener.open(req, timeout=5) as response:
                        return response.status, json.load(response)
                except HTTPError as error:
                    with error:
                        return error.code, json.load(error)

            def wait_for(predicate, label, timeout=30):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    value = predicate()
                    if value:
                        return value
                    time.sleep(0.025)
                raise RuntimeError(f"Timed out waiting for {label}")

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            for node in core.nodes:
                supervisor.start(node)
            wait_for(lambda: all(n["heartbeat"] > 0 for n in core.nodes.values()),
                     "three worker registrations")
            status, policy = request("/api/policy", {
                "consent": True, "mode": "manual", "budget": 60,
                "paused": False, "usage": "idle", "foreground_busy": False,
            })
            assert status == 200 and policy["effective_budget"] == 60, policy
            payload = {"count": 96, "batch": 16, "seed": 7,
                       "title": "Community quickstart: synthetic images"}
            key = "community-quickstart-v1"
            status, created = request("/api/jobs", payload, key)
            assert status == 201 and not created["duplicate"], created
            job_id = created["job_id"]

            def completed():
                status, job = request(f"/api/jobs/{job_id}")
                assert status == 200, job
                if job["status"] == "failed":
                    raise RuntimeError(f"Job failed: {job_id}")
                return job if job["status"] == "completed" else None

            job = wait_for(completed, "verified job completion")
            status, output = request(f"/api/jobs/{job_id}/results")
            assert status == 200 and len(output["results"]) == 96, output
            assert [r["image_id"] for r in output["results"]] == list(range(96))
            assert all(r["pixels"] == 128 * 128 and sum(r["histogram"]) == r["pixels"]
                       for r in output["results"])
            status, replay = request("/api/jobs", payload, key)
            assert status == 200 and replay == {"job_id": job_id, "duplicate": True}, replay
            conflict_status, conflict = request("/api/jobs", {**payload, "count": 97}, key)
            assert conflict_status == 409, conflict
            status, state = request("/api/state")
            assert status == 200 and state["totals"]["credits"] == 96, state["totals"]
            assert state["totals"]["accepted"] == 6
            summary = {
                "status": job["status"],
                "scope": "synthetic CPU statistics; one computer; no AI model",
                "worker_processes": len(supervisor.processes),
                "workers_with_accepted_chunks": sum(n["accepted"] > 0 for n in state["nodes"]),
                "accepted_images": len(output["results"]),
                "accepted_chunks": state["totals"]["accepted"],
                "demo_credits_without_monetary_value": state["totals"]["credits"],
                "duplicate_submission_reused_job": replay["duplicate"],
                "conflicting_submission_http_status": conflict_status,
                "first_result": output["results"][0],
            }
        finally:
            if supervisor is not None:
                supervisor.close()
            if server is not None:
                if thread is not None and thread.is_alive():
                    server.shutdown()
                    thread.join(timeout=5)
                server.server_close()
            core.close()
        assert all(p.poll() is not None for p in supervisor.processes.values())
        summary["all_worker_processes_stopped"] = True
    summary["temporary_database_removed"] = not Path(directory).exists()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run()
