"""Cooperative local CPU worker. No untrusted code, input files, GPU or shell execution."""
import argparse
import json
import os
import signal
import time
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from .compute import image_stats


def run(node, port):
    token = os.environ.pop("DEMO_WORKER_TOKEN")
    parent = os.getppid()

    def request(action, data=None):
        req = Request(f"http://127.0.0.1:{port}/internal/{action}",
                      json.dumps({"node": node, **(data or {})}).encode(),
                      {"Content-Type": "application/json", "Authorization": "Bearer " + token})
        with urlopen(req, timeout=5) as response:
            return json.load(response)

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0)))
    failures = 0
    while os.getppid() == parent:
        try:
            claimed = request("claim")
            lease = claimed["lease"]
            if not lease:
                time.sleep(0.15)
                continue
            if lease["fault"] == "exit":
                os._exit(17)  # Deliberate fault scenario: actual process exit without releasing lease.
            result, compute_ms, valid = [], 0.0, True
            q = claimed["policy"]["effective_budget"]
            for i in range(lease["start"], lease["stop"]):
                if (i - lease["start"]) % 8 == 0:
                    status = request("heartbeat", {"attempt_id": lease["attempt_id"]})
                    q = status["policy"]["effective_budget"]
                    if not status["valid"] or not q:
                        request("release", {"attempt_id": lease["attempt_id"]})
                        valid = False
                        break
                start = time.perf_counter()
                result.append(image_stats(lease["seed"], i))
                compute_ms += (time.perf_counter() - start) * 1000
            if valid:
                if lease["fault"] == "invalid":
                    result[0]["sum"] += 1
                payload = {"attempt_id": lease["attempt_id"], "results": result, "compute_ms": compute_ms}
                request("result", payload)
                if lease["fault"] == "replay":
                    request("result", payload)
                # Deliberate rest between finite image batches; not an OS CPU/GPU cap.
                rest = (compute_ms / 1000) * (100 / max(q, 1) - 1)
                until = time.monotonic() + rest
                while time.monotonic() < until and os.getppid() == parent:
                    time.sleep(max(0, min(0.1, until - time.monotonic())))
            failures = 0
        except (URLError, HTTPError, TimeoutError, OSError, KeyError, ValueError):
            failures += 1
            if failures >= 5:
                return
            time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True, choices=["cpu-1", "cpu-2", "cpu-3"])
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    run(args.node, args.port)
