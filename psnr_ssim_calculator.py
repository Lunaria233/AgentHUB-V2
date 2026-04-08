import argparse
import cv2
import numpy as np
from skimage.metrics import peak_signal_noise_ratio, structural_similarity


def calculate_psnr_ssim(img1_path, img2_path, channel_axis=None):
    """
    Calculate PSNR and SSIM between two images.
    
    Parameters:
    - img1_path: path to first image
    - img2_path: path to second image
    - channel_axis: int or None. If None, auto-detect; if 2, treat as RGB/BGR; if None for grayscale, uses 0.
    
    Returns:
    - psnr: float
    - ssim: float
    """
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)
    if img1 is None or img2 is None:
        raise ValueError("Failed to load one or both images.")

    # Convert BGR to RGB for consistency with skimage expectations
    img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
    img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)

    # Use RGB if both are color, else convert to grayscale
    if len(img1.shape) == 3 and len(img2.shape) == 3:
        # Ensure same dtype and range [0, 1]
        img1_norm = img1_rgb.astype(np.float64) / 255.0
        img2_norm = img2_rgb.astype(np.float64) / 255.0
        psnr_val = peak_signal_noise_ratio(img1_norm, img2_norm, data_range=1.0)
        ssim_val, _ = structural_similarity(img1_norm, img2_norm, channel_axis=2, full=True, data_range=1.0)
    else:
        img1_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        img2_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        img1_norm = img1_gray.astype(np.float64) / 255.0
        img2_norm = img2_gray.astype(np.float64) / 255.0
        psnr_val = peak_signal_noise_ratio(img1_norm, img2_norm, data_range=1.0)
        ssim_val, _ = structural_similarity(img1_norm, img2_norm, channel_axis=None, full=True, data_range=1.0)

    return psnr_val, ssim_val


def main():
    parser = argparse.ArgumentParser(description="Calculate PSNR and SSIM between two images.")
    parser.add_argument("img1", type=str, help="Path to the first image")
    parser.add_argument("img2", type=str, help="Path to the second image")
    args = parser.parse_args()

    try:
        psnr, ssim = calculate_psnr_ssim(args.img1, args.img2)
        print(f"PSNR: {psnr:.4f}")
        print(f"SSIM: {ssim:.4f}")
    except Exception as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()