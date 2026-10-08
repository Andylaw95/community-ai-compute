# Working example

The example demonstrates **submit → split → lease → execute → verify → record once → retrieve**.

It uses synthetic 128 × 128 grayscale images, not an AI model or customer data. Every image has a deterministic seed and index; its output contains a 16-bin histogram, pixel count, sum, sum of squares, and SHA-256 digest. The coordinator recomputes all of these. A matching hash alone is not the acceptance rule.

## Automatic example

From the repository root, with Python 3.12 on macOS or Linux:

```bash
python3 -m examples.quickstart
```

This explicitly opts in to a small local CPU job. No dependency installation or network download is needed. It starts three OS processes and a loopback-only HTTP server on an available port, uses a temporary SQLite database, and cleans up on completion or failure.

Read `first_result` to inspect an actual computed image result. The example checks 96 returned images, six accepted chunks, 96 valueless demo credits, reuse of a job on identical submission, and HTTP 409 when an idempotency key is reused with different content. Worker participation counts may vary with OS scheduling; the integration test separately checks that all three complete work.

An assertion or timeout exits unsuccessfully. This checks workflow and structural invariants, not an independent mathematical oracle: coordinator and workers currently share the computation implementation.

## Interactive example

```bash
python3 -m prototype.run --port 8765
```

Visit http://127.0.0.1:8765. The current interface is Traditional Chinese:

| Control | Meaning |
| --- | --- |
| 同意 / 套用設定 | Consent / apply settings |
| 提交批次 | Submit a batch |
| 取回 JSON | Retrieve verified results |
| 暫停貢獻 / 恢復貢獻 | Pause / resume contribution |
| 模擬前景遊戲 | Simulate a busy foreground application |
| 停止程序 / 啟動程序 | Stop / start one worker process |

The foreground switch supplies a simulated signal. There is no game, temperature, power, GPU, or real user-idle detection. The budget controls cooperative worker rest periods; it does not enforce a whole-device CPU/GPU limit or bound coordinator verification work.

Press **Ctrl+C in the terminal** to stop the server and workers. Closing the browser does not stop them. Nothing is installed for automatic startup. Jobs persist in `.runtime/demo.sqlite`, but each launch resets contribution consent. Use `--db .runtime/another-demo.sqlite` for a separate run; the demo retains at most 25 jobs per database.

## HTTP example

Start the interactive server and apply consent in its UI first. Then, in another terminal:

```bash
curl http://127.0.0.1:8765/api/jobs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: first-batch-001' \
  -d '{"count":96,"batch":16,"seed":7,"title":"My first synthetic batch"}'
```

Replace `JOB_ID` below with the returned `job_id`:

```bash
curl http://127.0.0.1:8765/api/jobs/JOB_ID
curl http://127.0.0.1:8765/api/jobs/JOB_ID/results
```

Results return HTTP 409 until all chunks are verified. Same key/content returns the same job; different content with that key returns HTTP 409. Inputs are limited to 1–4096 images, batches 4–128, and seeds 0–1000000. Arbitrary commands, models, URLs, files, and containers are not accepted.

## Checks

```bash
python3 -m unittest discover -s tests -v
python3 -m prototype.verify --output .runtime/my-verification.json
```

The second command adds three small timing trials; these are workflow measurements, not GPU or economic benchmarks. Linux CI runs functional tests and the automatic example. See [VALIDATION.md](VALIDATION.md) for the exact scope.

Keep the server on loopback. It has no remote-user authentication. Windows currently lacks a supported load-monitoring path and is not a supported target.
