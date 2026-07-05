import cv2
import numpy as np
from carm_multi_viewer.readers.base_reader import BaseReader
from carm_multi_viewer.models import ImageFrame

class ImageFileReader(BaseReader):
    """Reader for standard image formats like BMP, JPG, PNG, TIF."""
    
    SUPPORTED = (".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff")
    
    def can_handle(self, source: str) -> bool:
        return source.lower().endswith(self.SUPPORTED)
    
    def read(self, source: str, **kwargs) -> ImageFrame:
        # IMREAD_UNCHANGED keeps bit depth (e.g. 16-bit TIFF)
        img = cv2.imread(source, cv2.IMREAD_UNCHANGED)
        
        if img is None:
            raise ValueError(f"Unable to read image file: {source}")
            
        # Handle color vs grayscale
        if len(img.shape) == 3:
            # Convert to grayscale for consistent X-ray style viewing
            pixels = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            is_grayscale = False
        else:
            pixels = img
            is_grayscale = True
            
        bit_depth = 16 if img.dtype == np.uint16 else 8
        
        return ImageFrame(
            pixels=pixels,
            width=pixels.shape[1],
            height=pixels.shape[0],
            bit_depth=bit_depth,
            is_grayscale=True, # We forced it to grayscale for viewing
            metadata={"OriginalColor": not is_grayscale},
            source_format="image",
            file_path=source
        )
