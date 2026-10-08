# Synthetic image golden fixtures

`tests/test_compute_golden.py` freezes outputs for `(seed, image_id)` pairs
`(0, 0)`, `(7, 1)` and `(42, 3)`. They are original synthetic data, not photos.

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
with `image_stats` or `result_for`. All comparisons are exact integers/strings.
Histogram totals, bin bounds and moment inequalities provide additional checks;
an altered sum must fail the same equality assertion.

This protects against shared worker/verifier statistics regressions, not against
a defect in Python's cryptographic implementation: both derivations use hashlib.
It is a software fixture, not evidence about GPU hardware, remote workers or cost.
Intentional workload changes require explicit fixture review, not blind regeneration.

Run `python3 -m unittest discover -s tests -v` and
`python3 -m examples.quickstart` from the repository root.
