import numpy as np
from carm_multi_viewer.readers.base_reader import BaseReader
from carm_multi_viewer.models import ImageFrame

class RawReader(BaseReader):
    """Reader for RAW/BIN files. Requires manual parameters."""
    
    def __init__(self, width=1024, height=1024, dtype=np.uint16, header_size=0, endian="<"):
        self.width = width
        self.height = height
        self.dtype = dtype
        self.header_size = header_size
        self.endian = endian # '<' for little-endian, '>' for big-endian

    def can_handle(self, source: str) -> bool:
        return source.lower().endswith((".raw", ".bin"))

    def read(self, source: str, **kwargs) -> ImageFrame:
        # Override default params if provided in kwargs
        width = kwargs.get("width", self.width)
        height = kwargs.get("height", self.height)
        dtype = kwargs.get("dtype", self.dtype)
        header_size = kwargs.get("header_size", self.header_size)
        
        with open(source, "rb") as f:
            f.seek(header_size)
            data = f.read()
            
        # Convert data to numpy array
        arr = np.frombuffer(data, dtype=dtype)
        
        # Check if enough data exists
        expected_size = width * height
        if len(arr) < expected_size:
            arr = np.pad(arr, (0, expected_size - len(arr)))
        elif len(arr) > expected_size:
            arr = arr[:expected_size]
            
        pixels = arr.reshape((height, width))
        bit_depth = 16 if dtype in [np.uint16, np.int16] else 8
        
        return ImageFrame(
            pixels=pixels,
            width=width,
            height=height,
            bit_depth=bit_depth,
            is_grayscale=True,
            metadata={"HeaderSize": header_size, "DType": str(dtype)},
            source_format="raw",
            file_path=source
        )
