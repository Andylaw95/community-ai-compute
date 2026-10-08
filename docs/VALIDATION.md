# Launch validation

Date: 8 October 2026 (Asia/Hong_Kong). This report covers the local prototype, not a public compute network.

## Fresh functional run

Command: `python3 -m prototype.verify --output .runtime/community-launch-verification.json`

**15 tests passed; 0 failures; 0 errors; 0 skipped**, in 7.436 seconds on macOS 26.6.2, arm64, Python 3.12.1, 18 logical CPUs. No packages/models were installed. [Raw evidence](../evidence/community-launch-verification.json).

Coverage includes submission and idempotency conflicts, valid/invalid results, atomic credits, 16 concurrent result replays, stale/expired leases, bounded retries, pause/resume, simulated foreground policy, restart persistence and reset consent, actual worker exit/reassignment, and local API boundaries. Three distinct worker PIDs each completed work. Test workers were cleaned up.

## New self-contained example

Command: `python3 -m examples.quickstart`

Observed **96 accepted synthetic images, 6 chunks, 3 worker processes, 96 demo credits**. Same-key/same-content submission reused the job; changed content returned HTTP 409. Every worker stopped and the temporary database was removed. [Actual JSON output](../evidence/quickstart-output.json).

## Bounded local timing

Three trials, 768 images each, 24 chunks of 32, three workers, 60% per-worker cooperative duty-cycle target. Processes registered before timing; each wall time includes submission through verified completion, not cold startup or model loading.

| Trial | Wall seconds | Images/second | Worker compute seconds, summed | Verifier seconds, summed |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1.154 | 665.7 | 0.627 | 0.652 |
| 2 | 1.069 | 718.6 | 0.598 | 0.657 |
| 3 | 1.090 | 704.7 | 0.631 | 0.662 |

Median completion was **1.090 seconds**. Total verifier computation was **1.06×** worker computation. Durations wrap computation regions; they are not hardware CPU utilization or power measurements. Overlapping worker durations cannot be added to wall time. This was a shared-use computer, with one-minute OS load 6.74, not an isolated performance laboratory.

## Boundaries

- Synthetic CPU statistics, one device, loopback networking. No AI model, physical GPU, WAN, or external user.
- No evidence of cost advantage, energy savings, income, or paid demand. Credits have no value.
- The verifier shares the worker implementation and recomputes under the coordinator lock. Common bugs and verification throughput remain open problems.
- Foreground activity is simulated; no GPU partition or gaming compatibility was measured.
- No hostile-host, collusion/Sybil, sensitive-data, production accounting, or independent security audit claim.
- macOS is the environment of the measurements above. The repository CI separately runs Linux functional checks and the quickstart. A workflow definition alone is not a successful run; inspect its result.
- Windows is not supported or tested: the current load-monitoring path uses Unix facilities.

## Fresh browser verification

The existing Playwright/Chromium installation exercised a separate local server and database on port 8767. All 10 recorded checks passed: page identity, a newly submitted 384-image job and its output, pause during an active job, simulated foreground policy, worker stop/restart with a new PID, API/open-source navigation, desktop/mobile layout, and console/network checks. No console errors, warnings, failed requests, or horizontal overflow were observed. The second job had 4,096 images, making 4,480 images total for this UI run.

[Browser evidence](../evidence/browser-verification.json) · [Dashboard screenshot](images/local-prototype.png)

The script accepts `--url` and `--output` so a fresh instance can be checked without touching another preview. Playwright/Chromium are optional development tools, not runtime dependencies.

## Repeat

```bash
python3 -m unittest discover -s tests -v
python3 -m examples.quickstart
python3 -m prototype.verify --output .runtime/my-verification.json
```

Do not overwrite the checked-in evidence when reporting a new run. Include the commit and environment with your own output.
