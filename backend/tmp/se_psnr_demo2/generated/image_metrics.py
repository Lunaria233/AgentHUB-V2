import numpy as np
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

def compute_psnr_ssim(
    img1,
    img2
):
    """
    Compute PSNR and SSIM between two images.
    Supports input as list[list[int]] or numpy.ndarray.
    Both images must have same shape and be 2D or 3D (grayscale or RGB).
    
    Returns:
        dict: {'psnr': float, 'ssim': float}
    """
    def to_uint8_ndarray(img):
        if isinstance(img, list):
            img = np.array(img)
        if not isinstance(img, np.ndarray):
            raise TypeError(f"Unsupported image type: {type(img)}")
        if img.dtype == bool:
            img = img.astype(np.uint8) * 255
        elif img.dtype != np.uint8:
            # Clamp and cast
            img = np.clip(img, 0, 255).astype(np.uint8)
        return img

    arr1 = to_uint8_ndarray(img1)
    arr2 = to_uint8_ndarray(img2)

    if arr1.shape != arr2.shape:
        raise ValueError(f"Image shapes differ: {arr1.shape} vs {arr2.shape}")

    if arr1.ndim not in (2, 3):
        raise ValueError(f"Unsupported number of dimensions: {arr1.ndim}")

    # Ensure same dtype
    arr1 = arr1.astype(np.uint8)
    arr2 = arr2.astype(np.uint8)

    # PSNR
    psnr_val = peak_signal_noise_ratio(arr1, arr2, data_range=255)

    # SSIM: handle small images by adapting win_size
    min_dim = min(arr1.shape[:2])
    # win_size must be odd, >= 3, <= min_dim
    win_size = min(7, min_dim)
    if win_size < 3:
        win_size = 3
    elif win_size % 2 == 0:
        win_size -= 1

    # For 2D: use channel_axis=None; for 3D RGB: use channel_axis=-1
    channel_axis = -1 if arr1.ndim == 3 else None
    ssim_val = structural_similarity(
        arr1,
        arr2,
        win_size=win_size,
        channel_axis=channel_axis,
        data_range=255
    )

    return {
        'psnr': float(psnr_val),
        'ssim': float(ssim_val)
    }