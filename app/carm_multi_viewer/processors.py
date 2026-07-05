import numpy as np
import cv2

# ── Available filter names (shown in dropdowns) ──────────────────────────────
FILTER_NAMES = [
    "Normal",
    "Invert",
    "CLAHE (Enhance Contrast)",
    "Edge Enhance",
    "Bone Highlight",
    "Soft Tissue",
    "False Color (Hot)",
    "False Color (Cool)",
    "False Color (Jet)",
    "Sharpen",
    "Denoise",
]

def to_display_8bit(img: np.ndarray, window_center: float = None, window_width: float = None) -> np.ndarray:
    """Converts a high bit-depth or float image to 8-bit for display with optional windowing."""
    img_float = img.astype(np.float32)

    if window_center is not None and window_width is not None:
        low = window_center - window_width / 2
        high = window_center + window_width / 2
        img_float = np.clip(img_float, low, high)
        if high > low:
            img_float = (img_float - low) / (high - low) * 255.0
        else:
            img_float = np.zeros_like(img_float)
    else:
        img_min = img_float.min()
        img_max = img_float.max()
        if img_max > img_min:
            img_float = (img_float - img_min) / (img_max - img_min) * 255.0
        else:
            img_float = np.zeros_like(img_float)

    return img_float.astype(np.uint8)


def apply_filter(img: np.ndarray, filter_name: str) -> np.ndarray:
    """
    Applies the selected filter to an 8-bit grayscale image.
    Returns either a grayscale (H,W) or color (H,W,3) uint8 array.
    """
    if filter_name == "Normal":
        return img

    elif filter_name == "Invert":
        return 255 - img

    elif filter_name == "CLAHE (Enhance Contrast)":
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        return clahe.apply(img)

    elif filter_name == "Edge Enhance":
        kernel = np.array([[0, -1, 0],
                           [-1,  5, -1],
                           [0, -1, 0]], dtype=np.float32)
        sharpened = cv2.filter2D(img, -1, kernel)
        blended = cv2.addWeighted(img, 0.6, sharpened, 0.4, 0)
        return blended

    elif filter_name == "Bone Highlight":
        # Emphasize bright bone structures (threshold upper half)
        _, bone_mask = cv2.threshold(img, 160, 255, cv2.THRESH_BINARY)
        enhanced = cv2.addWeighted(img, 0.7, bone_mask, 0.3, 0)
        return enhanced

    elif filter_name == "Soft Tissue":
        # Gamma correction to bring out midtone soft tissue
        gamma = 1.8
        lut = np.array([((i / 255.0) ** (1.0 / gamma)) * 255 for i in range(256)], dtype=np.uint8)
        return cv2.LUT(img, lut)

    elif filter_name == "False Color (Hot)":
        color = cv2.applyColorMap(img, cv2.COLORMAP_HOT)
        return cv2.cvtColor(color, cv2.COLOR_BGR2RGB)

    elif filter_name == "False Color (Cool)":
        color = cv2.applyColorMap(img, cv2.COLORMAP_COOL)
        return cv2.cvtColor(color, cv2.COLOR_BGR2RGB)

    elif filter_name == "False Color (Jet)":
        color = cv2.applyColorMap(img, cv2.COLORMAP_JET)
        return cv2.cvtColor(color, cv2.COLOR_BGR2RGB)

    elif filter_name == "Sharpen":
        kernel = np.array([[-1, -1, -1],
                           [-1,  9, -1],
                           [-1, -1, -1]], dtype=np.float32)
        return cv2.filter2D(img, -1, kernel)

    elif filter_name == "Denoise":
        return cv2.fastNlMeansDenoising(img, h=10)

    return img


def apply_lut(img: np.ndarray, invert: bool = False) -> np.ndarray:
    """Legacy: Applies basic LUT inversion."""
    if invert:
        return 255 - img
    return img
