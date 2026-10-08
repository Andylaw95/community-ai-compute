"""Fixed, deterministic image statistics; inputs are synthetic, never customer files."""
import hashlib

WORKLOAD = "synthetic-grayscale-statistics/v1"
SIDE = 128


def image_stats(seed, image_id):
    pixels = hashlib.shake_256(f"{WORKLOAD}:{seed}:{image_id}".encode()).digest(SIDE * SIDE)
    histogram = [0] * 16
    total = squares = 0
    for pixel in pixels:
        histogram[pixel // 16] += 1
        total += pixel
        squares += pixel * pixel
    return {"image_id": image_id, "pixels": len(pixels), "sum": total,
            "sum_squares": squares, "histogram": histogram,
            "sha256": hashlib.sha256(pixels).hexdigest()}


def result_for(seed, start, stop):
    return [image_stats(seed, i) for i in range(start, stop)]
