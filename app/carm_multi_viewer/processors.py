import numpy as np
import cv2

def to_display_8bit(img: np.ndarray, window_center: float = None, window_width: float = None) -> np.ndarray:
    """
    Converts a high bit-depth or float image to 8-bit for display.
    Applies window leveling if parameters are provided.
    """
    img_float = img.astype(np.float32)
    
    # If window parameters are provided, apply windowing
    if window_center is not None and window_width is not None:
        low = window_center - window_width / 2
        high = window_center + window_width / 2
        img_float = np.clip(img_float, low, high)
        
        # Normalize to [0, 255] within the window
        if high > low:
            img_float = (img_float - low) / (high - low) * 255.0
        else:
            img_float = np.zeros_like(img_float)
    else:
        # Fallback: simple min-max normalization
        img_min = img_float.min()
        img_max = img_float.max()
        if img_max > img_min:
            img_float = (img_float - img_min) / (img_max - img_min) * 255.0
        else:
            img_float = np.zeros_like(img_float)
            
    return img_float.astype(np.uint8)

def apply_lut(img: np.ndarray, invert: bool = False) -> np.ndarray:
    """Applies basic LUT operations like inversion."""
    if invert:
        return 255 - img
    return img
