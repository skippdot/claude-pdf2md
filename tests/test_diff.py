from __future__ import annotations

import numpy as np

from claude_pdf2md.diff import pixel_diff, ssim


def test_ssim_identical_images_is_one():
    img = np.random.RandomState(0).randint(0, 255, size=(64, 64), dtype=np.uint8).astype(np.float32)
    assert ssim(img, img) > 0.999


def test_ssim_inverted_images_is_low():
    img = np.full((64, 64), 250.0, dtype=np.float32)
    inv = np.full((64, 64), 5.0, dtype=np.float32)
    assert ssim(img, inv) < 0.1


def test_pixel_diff_zero_when_equal():
    a = np.zeros((8, 8, 3), dtype=np.uint8)
    assert pixel_diff(a, a) == 0.0


def test_pixel_diff_one_when_all_different():
    a = np.zeros((8, 8, 3), dtype=np.uint8)
    b = np.full_like(a, 255)
    assert pixel_diff(a, b) == 1.0
