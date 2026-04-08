from __future__ import annotations

from generated.image_metrics import compute_psnr_ssim


def main() -> None:
    # Build two tiny deterministic grayscale images.
    image_a = [
        [0, 64, 128, 255],
        [16, 80, 144, 240],
        [32, 96, 160, 224],
        [48, 112, 176, 208],
    ]
    image_b = [
        [0, 62, 130, 250],
        [20, 78, 146, 238],
        [30, 100, 158, 220],
        [50, 108, 180, 206],
    ]
    result = compute_psnr_ssim(image_a, image_b)
    assert isinstance(result, dict), "result must be a dict"
    assert "psnr" in result and "ssim" in result, "result must contain psnr/ssim"
    psnr = float(result["psnr"])
    ssim = float(result["ssim"])
    assert psnr > 0.0, "psnr should be positive"
    assert 0.0 <= ssim <= 1.0, "ssim should be within [0, 1]"
    print({"psnr": psnr, "ssim": ssim})


if __name__ == "__main__":
    main()
