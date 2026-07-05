from dataclasses import dataclass, field
import numpy as np
from typing import Optional, Dict, Any

@dataclass
class ImageFrame:
    """Common internal representation for all image formats."""
    pixels: np.ndarray          # numpy array (usually grayscale)
    width: int
    height: int
    bit_depth: int              # 8 / 12 / 14 / 16
    is_grayscale: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_format: str = "unknown"  # dicom / jpg / raw / video / live
    file_path: Optional[str] = None
