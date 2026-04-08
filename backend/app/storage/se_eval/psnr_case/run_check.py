from __future__ import annotations

import numpy as np

from psnr_ssim import compute_psnr_ssim


def main() -> None:
    img_a = np.zeros((16, 16), dtype=np.uint8)
    img_b = np.ones((16, 16), dtype=np.uint8) * 10
    metrics = compute_psnr_ssim(img_a, img_b, data_range=255)
    assert isinstance(metrics, dict)
    assert "psnr" in metrics and "ssim" in metrics
    print("ok", metrics)


if __name__ == "__main__":
    main()
