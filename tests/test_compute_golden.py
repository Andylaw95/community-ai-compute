"""Frozen synthetic-image outputs derived without importing prototype.compute.

See docs/COMPUTE-GOLDEN.md for the independent derivation and its limits.
"""
import copy
import unittest

from prototype.compute import image_stats


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
                self.assertEqual(image_stats(seed, expected["image_id"]), expected)

    def test_fixtures_satisfy_grayscale_invariants(self):
        for _, expected in GOLDEN:
            histogram = expected["histogram"]
            self.assertEqual(len(histogram), 16)
            self.assertEqual(sum(histogram), expected["pixels"])
            self.assertLessEqual(sum(16 * b * n for b, n in enumerate(histogram)), expected["sum"])
            self.assertGreaterEqual(sum((16 * b + 15) * n for b, n in enumerate(histogram)), expected["sum"])
            self.assertLessEqual(expected["sum"] ** 2, expected["pixels"] * expected["sum_squares"])
            self.assertLessEqual(expected["sum_squares"], 255 * expected["sum"])

    def test_an_altered_field_fails_the_same_equality_check(self):
        seed, expected = GOLDEN[0]
        altered = copy.deepcopy(image_stats(seed, expected["image_id"]))
        altered["sum"] += 1
        with self.assertRaises(AssertionError):
            self.assertEqual(altered, expected)
