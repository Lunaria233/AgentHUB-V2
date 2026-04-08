"""Unit tests for image_metrics module."""

import unittest
import numpy as np
from app.image_metrics import psnr, ssim


class TestPSNR(unittest.TestCase):
    """Test cases for PSNR function."""
    
    def test_identical_images(self):
        """PSNR should be infinite for identical images."""
        img = np.zeros((10, 10))
        result = psnr(img, img)
        self.assertEqual(result, float('inf'))
    
    def test_different_images(self):
        """PSNR should be finite for different images."""
        img_a = np.zeros((10, 10))
        img_b = np.ones((10, 10)) * 128
        result = psnr(img_a, img_b)
        self.assertGreater(result, 0)
        self.assertLess(result, 100)


class TestSSIM(unittest.TestCase):
    """Test cases for SSIM function."""
    
    def test_identical_images(self):
        """SSIM should be 1.0 for identical images."""
        img = np.random.rand(10, 10).astype(np.float64)
        result = ssim(img, img)
        self.assertAlmostEqual(result, 1.0, places=5)
    
    def test_different_images(self):
        """SSIM should be less than 1.0 for different images."""
        img_a = np.zeros((10, 10)).astype(np.float64)
        img_b = np.ones((10, 10)).astype(np.float64)
        result = ssim(img_a, img_b)
        self.assertLess(result, 1.0)
        self.assertGreaterEqual(result, 0.0)


if __name__ == '__main__':
    unittest.main()
