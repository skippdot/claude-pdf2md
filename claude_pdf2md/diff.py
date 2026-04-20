from __future__ import annotations

import numpy as np


def pixel_diff(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")
    threshold = 32
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=-1)
    diff_mask = delta > threshold
    return float(diff_mask.mean())


def ssim(a: np.ndarray, b: np.ndarray, win_size: int = 11) -> float:
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")
    # Single-scale SSIM on luma with a uniform box kernel — sufficient for the
    # "does my markdown render roughly like the PDF" quality gate. For
    # reference-grade work, use skimage's gaussian-windowed SSIM instead.
    k1, k2, L = 0.01, 0.03, 255.0
    c1 = (k1 * L) ** 2
    c2 = (k2 * L) ** 2

    a = a.astype(np.float32)
    b = b.astype(np.float32)

    mu_a = _box_filter(a, win_size)
    mu_b = _box_filter(b, win_size)
    mu_aa = _box_filter(a * a, win_size)
    mu_bb = _box_filter(b * b, win_size)
    mu_ab = _box_filter(a * b, win_size)

    var_a = np.clip(mu_aa - mu_a * mu_a, 0, None)
    var_b = np.clip(mu_bb - mu_b * mu_b, 0, None)
    cov_ab = mu_ab - mu_a * mu_b

    num = (2 * mu_a * mu_b + c1) * (2 * cov_ab + c2)
    den = (mu_a * mu_a + mu_b * mu_b + c1) * (var_a + var_b + c2)
    ssim_map = num / np.clip(den, 1e-8, None)
    return float(ssim_map.mean())


def _box_filter(img: np.ndarray, win: int) -> np.ndarray:
    if win <= 1:
        return img
    k = win
    pad = k // 2
    padded = np.pad(img.astype(np.float64), pad, mode="edge")
    H, W = padded.shape
    # Standard summed-area table trick: prepend a zero row/col so rectangle
    # sums can be indexed without wrap-around.
    integral = np.zeros((H + 1, W + 1), dtype=np.float64)
    integral[1:, 1:] = np.cumsum(np.cumsum(padded, axis=0), axis=1)
    s = integral[k:, k:] - integral[:-k, k:] - integral[k:, :-k] + integral[:-k, :-k]
    return (s / (k * k)).astype(np.float32)
