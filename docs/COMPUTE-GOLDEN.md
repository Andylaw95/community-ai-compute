# Synthetic image golden fixtures

`tests/test_compute_golden.py` freezes outputs for `(seed, image_id)` pairs
`(0, 0)`, `(7, 1)` and `(42, 3)`. They are original synthetic data, not photos.

The worker calls `image_stats` directly; the verifier calls `result_for`, which
uses the same `image_stats` implementation. Agreement between those paths alone
cannot detect a shared statistics bug.

The source of truth is the v1 workload definition: ASCII bytes
`synthetic-grayscale-statistics/v1:<seed>:<image_id>`, SHAKE-256 output of
16,384 bytes, then integer grayscale statistics. A separate stdlib-only
calculation generated the constants without importing `prototype.compute`:

```python
import hashlib

seed, image_id = 7, 1
payload = f"synthetic-grayscale-statistics/v1:{seed}:{image_id}".encode("ascii")
pixels = hashlib.shake_256(payload).digest(16384)
count = len(pixels)
total = sum(pixels)
squares = sum(x ** 2 for x in pixels)
histogram = [sum(1 for x in pixels if 16 * b <= x < 16 * (b + 1))
             for b in range(16)]
digest = hashlib.sha256(pixels).hexdigest()
print(count, total, squares, histogram, digest)
```

Unlike production's single accumulation loop, the derivation uses separate
reductions and interval membership for each histogram bin. Tests compare the
complete production result to literal constants, never regenerate expectations
with `image_stats` or `result_for`. Tests require actual image IDs, pixel counts,
sums, sums of squares and histogram entries to have the exact `int` type,
excluding floats and booleans even when Python considers their values equal.
The histogram must be a list and the digest a string; full result equality also
checks every key, value and histogram position. Nonnegative histogram counts,
histogram totals, bin bounds and moment inequalities check fixture consistency.

A separate coordinator test submits the literal `(0, 0)` result and checks
acceptance and credit. Negative cases alter each result field and substitute
numerically equal floats or a boolean. The verifier must reject each case
without credit, requeue it, and accept the correct literal result on retry.

This protects against shared worker/verifier statistics regressions, not against
a defect in Python's cryptographic implementation: both derivations use hashlib.
It is a software fixture, not evidence about GPU hardware, remote workers or cost.
Intentional workload changes require explicit fixture review, not blind regeneration.

Run `python3 -m unittest tests.test_compute_golden -v` for the focused tests,
then `python3 -m unittest discover -s tests -v` and
`python3 -m examples.quickstart` from the repository root.
