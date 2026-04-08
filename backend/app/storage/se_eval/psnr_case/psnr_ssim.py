from __future__ import annotations

from skimage.metrics import peak_signal_noise_ratio, structural_similarity


def compute_psnr_ssim(img1, img2, data_range: int = 255) -> dict[str, float]:
    """Return PSNR and SSIM for two grayscale image arrays."""
    psnr = peak_signal_noise_ratio(img1, img2, data_range=data_range)
    ssim = structural_similarity(img1, img2, data_range=data_range)
    return {"psnr": float(psnr), "ssim": float(ssim)}
