"""Image metrics module for PSNR and SSIM calculation."""

import numpy as np
from skimage.metrics import peak_signal_noise_ratio, structural_similarity


def psnr(image_a: np.ndarray, image_b: np.ndarray) -> float:
    """Calculate Peak Signal-to-Noise Ratio between two images.
    
    Args:
        image_a: First image as numpy array
        image_b: Second image as numpy array
        
    Returns:
        PSNR value in decibels
    """
    return peak_signal_noise_ratio(image_a, image_b)


def ssim(image_a: np.ndarray, image_b: np.ndarray, data_range: int = None) -> float:
    """Calculate Structural Similarity Index between two images.
    
    Args:
        image_a: First image as numpy array
        image_b: Second image as numpy array
        data_range: Data range of the input images (default: max - min)
        
    Returns:
        SSIM value between 0 and 1
    """
    if data_range is None:
        data_range = image_a.max() - image_a.min()
    return structural_similarity(image_a, image_b, data_range=data_range)
