"""Frozen synthetic-image outputs derived without importing prototype.compute.

See docs/COMPUTE-GOLDEN.md for the independent derivation and its limits.
"""
import copy
import unittest

from prototype.compute import image_stats
from prototype.engine import Coordinator


GOLDEN = (
    (0, {"image_id": 0, "pixels": 16384, "sum": 2086179,
         "sum_squares": 354703721,
         "histogram": [1030, 971, 1037, 1065, 1010, 1057, 1048, 1037,
                       964, 993, 1069, 1034, 1013, 1037, 1006, 1013],
         "sha256": "6e88913111ceddc80733ca0a8803c3c0be98a930eba60b901c429cb1ccb8e9ee"}),
    (7, {"image_id": 1, "pixels": 16384, "sum": 2085801,
         "sum_squares": 354834327,
         "histogram": [1026, 997, 1060, 1004, 1038, 1045, 1024, 1001,
                       1078, 1023, 1017, 1018, 966, 1034, 1027, 1026],
         "sha256": "2740cbbb7b88be27e5eb3256c748a927a81d1ca8b2f3706d588a072ffa100b77"}),
    (42, {"image_id": 3, "pixels": 16384, "sum": 2116143,
          "sum_squares": 362418775,
          "histogram": [989, 964, 1029, 981, 1027, 1035, 938, 979,
                        1107, 1061, 1047, 1035, 1016, 1083, 1055, 1038],
          "sha256": "ca2e344c730b01085c3ed2428c79615900837465726a9734d3d9eeb137238525"}),
)


class GoldenComputeTests(unittest.TestCase):
    def test_image_statistics_match_frozen_outputs(self):
        for seed, expected in GOLDEN:
            with self.subTest(seed=seed, image_id=expected["image_id"]):
                actual = image_stats(seed, expected["image_id"])
                for field in ("image_id", "pixels", "sum", "sum_squares"):
                    self.assertIs(type(actual[field]), int, field)
                self.assertIs(type(actual["histogram"]), list)
                for index, count in enumerate(actual["histogram"]):
                    self.assertIs(type(count), int, f"histogram[{index}]")
                self.assertIs(type(actual["sha256"]), str)
                self.assertEqual(actual, expected)

    def test_fixtures_satisfy_grayscale_invariants(self):
        for _, expected in GOLDEN:
            histogram = expected["histogram"]
            self.assertEqual(len(histogram), 16)
            self.assertTrue(all(count >= 0 for count in histogram))
            self.assertEqual(sum(histogram), expected["pixels"])
            self.assertLessEqual(sum(16 * b * n for b, n in enumerate(histogram)), expected["sum"])
            self.assertGreaterEqual(sum((16 * b + 15) * n for b, n in enumerate(histogram)), expected["sum"])
            self.assertLessEqual(expected["sum"] ** 2, expected["pixels"] * expected["sum_squares"])
            self.assertLessEqual(expected["sum_squares"], 255 * expected["sum"])

    def claim_frozen_image(self):
        coordinator = Coordinator(":memory:", clock=lambda: 1000.0)
        self.addCleanup(coordinator.close)
        coordinator.nodes["cpu-1"]["alive"] = True
        coordinator.set_policy({"consent": True, "mode": "manual", "budget": 30})
        coordinator.submit({"count": 1, "batch": 4, "seed": GOLDEN[0][0]}, "golden")
        return coordinator, coordinator.claim("cpu-1")["lease"]

    def test_verifier_accepts_frozen_result(self):
        coordinator, lease = self.claim_frozen_image()
        reply = coordinator.accept("cpu-1", {
            "attempt_id": lease["attempt_id"], "results": [copy.deepcopy(GOLDEN[0][1])],
        })
        self.assertEqual(reply["status"], "accepted")
        self.assertEqual(reply["credits_awarded"], 1)
        self.assertEqual(coordinator.results(lease["job_id"])["results"], [GOLDEN[0][1]])

    def test_verifier_rejects_altered_fields_without_credit(self):
        _, expected = GOLDEN[0]
        changes = [(field, expected[field] + 1)
                   for field in ("image_id", "pixels", "sum", "sum_squares")]
        changes.extend([
            ("histogram", [expected["histogram"][0] + 1, *expected["histogram"][1:]]),
            ("sha256", "0" * 64),
        ])
        # Numerically equal floats/bools must still violate the integer contract.
        changes.extend((field, float(expected[field]))
                       for field in ("image_id", "pixels", "sum", "sum_squares"))
        changes.extend([
            ("histogram", [float(count) for count in expected["histogram"]]),
            ("image_id", False),
        ])
        for field, value in changes:
            with self.subTest(field=field, value=value):
                coordinator, lease = self.claim_frozen_image()
                altered = copy.deepcopy(expected)
                altered[field] = value
                reply = coordinator.accept("cpu-1", {
                    "attempt_id": lease["attempt_id"], "results": [altered],
                })
                self.assertEqual(reply["status"], "invalid")
                self.assertEqual(reply["credits_awarded"], 0)
                self.assertEqual(coordinator.snapshot()["totals"]["credits"], 0)
                retry = coordinator.claim("cpu-1")["lease"]
                self.assertIsNotNone(retry)
                accepted = coordinator.accept("cpu-1", {
                    "attempt_id": retry["attempt_id"], "results": [copy.deepcopy(expected)],
                })
                self.assertEqual(accepted["status"], "accepted")
                self.assertEqual(accepted["credits_awarded"], 1)
