"""Run bounded functional tests and three local timing trials; writes requested evidence."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import time
import unittest

from tests.test_prototype import IntegrationTests, Running


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("evidence/local-verification.json"))
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover("tests")
    start = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    elapsed = time.perf_counter() - start
    report = {"utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "system": platform.platform(), "logical_cpus": os.cpu_count(), "load_1m": os.getloadavg()[0],
              "tests": {"run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                        "skipped": len(result.skipped), "seconds": elapsed},
              "integration_evidence": IntegrationTests.evidence, "timing_trials": []}
    # unittest discovery imports the same file by a top-level name; retrieve its evidence.
    module = sys.modules.get("test_prototype")
    if module:
        report["integration_evidence"] = module.IntegrationTests.evidence
    if result.wasSuccessful():
        with Running() as running:
            running.enable()
            for i in range(3):
                before = running.core.snapshot()["totals"]
                start = time.perf_counter()
                jid = running.job(key=f"timing-{i}", count=768, batch=32)
                running.done(jid)
                duration = time.perf_counter() - start
                after = running.core.snapshot()["totals"]
                report["timing_trials"].append({"job_id": jid, "images": 768, "image_side": 128,
                    "chunks": 24, "workers": 3, "manual_budget_percent": 60,
                    "wall_seconds": duration, "accepted_images_per_second": 768 / duration,
                    "worker_compute_seconds": (after["compute_ms"] - before["compute_ms"]) / 1000,
                    "verifier_compute_seconds": (after["verify_ms"] - before["verify_ms"]) / 1000,
                    "credits": after["credits"] - before["credits"]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"Evidence: {args.output.resolve()}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
