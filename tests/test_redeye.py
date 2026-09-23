#!/usr/bin/env python3
"""Red-eye removal: the pure-numpy face finder and the pupil fix.

    python3 tests/test_redeye.py

Needs numpy and Pillow. Where OpenCV is installed, the numpy network and the
numpy shrink are also checked against OpenCV's own.
"""

import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    import numpy as np
    from PIL import Image
    from digicarlo import redeye
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False


def eye_patch(size=40, pupil=6, pupil_rgb=(205, 32, 28), skin=(206, 152, 128)):
    """A synthetic eye: skin, the white, a brown iris and a pupil."""
    yy, xx = np.mgrid[:size, :size]
    c = (size - 1) / 2.0
    img = np.zeros((size, size, 3), np.uint8)
    img[:] = skin
    white = ((xx - c) / (size * 0.45)) ** 2 + ((yy - c) / (size * 0.28)) ** 2 < 1
    img[white] = (236, 232, 226)
    iris = (xx - c) ** 2 + (yy - c) ** 2 < (pupil * 1.9) ** 2
    img[iris] = (92, 62, 44)
    img[(xx - c) ** 2 + (yy - c) ** 2 < pupil ** 2] = pupil_rgb
    img[(xx - c + 2) ** 2 + (yy - c + 2) ** 2 < 2.5] = (250, 250, 250)   # catchlight
    return img


@unittest.skipUnless(HAVE_NUMPY, "numpy or Pillow is not installed")
class NetworkTests(unittest.TestCase):
    def test_model_reads(self):
        net = redeye._net()
        ops = [n["op"] for n in net.nodes]
        self.assertEqual(ops.count("Conv"), 53)
        self.assertEqual(len(net.outputs), 12)
        self.assertEqual(net.inputs, ["input"])

    def test_nothing_in_a_blank_picture(self):
        self.assertEqual(redeye.detect(np.zeros((240, 320, 3), np.uint8)).shape, (0, 15))

    @unittest.skipUnless(HAVE_CV2, "OpenCV is not installed")
    def test_network_matches_opencv(self):
        rng = np.random.default_rng(7)
        img = rng.integers(0, 256, (192, 256, 3), dtype=np.uint8)
        blob = cv2.dnn.blobFromImage(img)
        ref = cv2.dnn.readNet(redeye.MODEL)
        ref.setInput(blob)
        names = redeye._net().outputs
        want = dict(zip(names, ref.forward(names)))
        got = redeye._net().run(blob)
        for k in names:
            self.assertLess(float(np.abs(want[k].reshape(-1) - got[k].reshape(-1)).max()), 1e-4, k)

    def test_shrink_keeps_a_flat_colour(self):
        img = np.full((300, 401, 3), 137, np.uint8)
        small = redeye.shrink(img, 0.3)
        self.assertEqual(small.shape, (90, 120, 3))
        self.assertTrue((small == 137).all())

    @unittest.skipUnless(HAVE_CV2, "OpenCV is not installed")
    def test_shrink_matches_opencv_area(self):
        rng = np.random.default_rng(3)
        img = rng.integers(0, 256, (523, 701, 3), dtype=np.uint8)
        s = 0.4913
        want = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        got = redeye.shrink(img, s)
        self.assertEqual(want.shape, got.shape)
        self.assertLessEqual(int(np.abs(want.astype(int) - got.astype(int)).max()), 1)


@unittest.skipUnless(HAVE_NUMPY, "numpy or Pillow is not installed")
class PupilTests(unittest.TestCase):
    def test_a_red_pupil_is_found(self):
        mask = redeye.red_mask(eye_patch())
        self.assertIsNotNone(mask)
        ys, xs = np.nonzero(mask)
        self.assertLess(abs(xs.mean() - 19.5), 2)
        self.assertLess(abs(ys.mean() - 19.5), 2)
        self.assertLess(mask.sum(), 40 * 40 * 0.2)

    def test_a_dark_pupil_is_left_alone(self):
        self.assertIsNone(redeye.red_mask(eye_patch(pupil_rgb=(20, 18, 16))))

    def test_red_fabric_is_not_an_eye(self):
        patch = np.zeros((40, 40, 3), np.uint8)
        patch[:] = (190, 30, 30)
        self.assertIsNone(redeye.red_mask(patch))

    def test_red_running_off_the_patch_is_not_an_eye(self):
        patch = eye_patch()
        patch[15:25, 0:22] = (205, 32, 28)
        patch[15:25, 18:26] = (205, 32, 28)
        self.assertIsNone(redeye.red_mask(patch))

    def test_ruddy_skin_is_not_red_enough(self):
        self.assertIsNone(redeye.red_mask(eye_patch(pupil_rgb=(200, 120, 105))))


@unittest.skipUnless(HAVE_NUMPY, "numpy or Pillow is not installed")
class FixTests(unittest.TestCase):
    def test_both_eyes_fixed_and_nothing_else_touched(self):
        img = np.zeros((300, 400, 3), np.uint8)
        img[:] = (206, 152, 128)
        eyes = ((160, 130), (240, 130))
        d = 80
        rad = int(d * 0.26)
        for cx, cy in eyes:
            img[cy - 20:cy + 20, cx - 20:cx + 20] = eye_patch()
        face = np.zeros((1, 15), np.float32)
        face[0, :4] = (110, 70, 180, 200)
        face[0, 4:8] = (eyes[0][0] - 0.5, eyes[0][1] - 0.5, eyes[1][0] - 0.5, eyes[1][1] - 0.5)
        face[0, 14] = 0.95
        out, fixed, _ = redeye.remove_red_eye(Image.fromarray(img), faces=face)
        out = np.asarray(out)
        self.assertEqual(len(fixed), 2)
        for cx, cy in eyes:
            r, g, b = (int(v) for v in out[cy + 2, cx + 1])
            self.assertLess(r, 1.3 * max(g, b, 1), "pupil still red: %r" % ((r, g, b),))
            self.assertLess(r, 90)
        untouched = np.ones(img.shape[:2], bool)
        for x, y, w, h in fixed:
            untouched[y:y + h, x:x + w] = False
        self.assertTrue(np.array_equal(out[untouched], img[untouched]))
        self.assertEqual(fixed[0][2], 2 * rad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
