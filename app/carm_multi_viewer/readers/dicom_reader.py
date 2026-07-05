import pydicom
import numpy as np
from carm_multi_viewer.readers.base_reader import BaseReader
from carm_multi_viewer.models import ImageFrame

class DicomReader(BaseReader):
    """Reader for DICOM files, including those without .dcm extension."""
    
    def can_handle(self, source: str) -> bool:
        try:
            # Check for DICM signature (offset 128)
            with open(source, "rb") as f:
                f.seek(128)
                header = f.read(4)
                if header == b"DICM":
                    return True
            
            # Or extension check
            if source.lower().endswith(".dcm"):
                return True
                
            # Or try reading with force=True (slow fallback)
            pydicom.dcmread(source, stop_before_pixels=True, force=True)
            return True
        except Exception:
            return False

    def read(self, source: str, **kwargs) -> ImageFrame:
        ds = pydicom.dcmread(source, force=True)
        
        if not hasattr(ds, "pixel_array"):
            raise ValueError("DICOM file does not contain pixel data")
            
        pixels = ds.pixel_array
        
        # Fix shape to guarantee 2D for the ImageViewer
        if pixels.ndim > 2:
            # Multi-frame (first dimension is number of frames)
            if hasattr(ds, "NumberOfFrames") and int(ds.NumberOfFrames) > 1:
                pixels = pixels[0]
            
            # If still > 2 (e.g. color image: height, width, channels)
            if pixels.ndim > 2:
                pixels = np.mean(pixels, axis=-1)
                
        # Get bit depth metadata
        bit_depth = int(getattr(ds, "BitsStored", getattr(ds, "BitsAllocated", 16)))
        
        # Extract basic metadata
        metadata = {
            "PatientName": str(getattr(ds, "PatientName", "Unknown")),
            "PatientID": str(getattr(ds, "PatientID", "Unknown")),
            "Modality": str(getattr(ds, "Modality", "Unknown")),
            "StudyDate": str(getattr(ds, "StudyDate", "Unknown")),
            "WindowCenter": getattr(ds, "WindowCenter", None),
            "WindowWidth": getattr(ds, "WindowWidth", None),
        }
        
        # Normalize window params if they are lists
        for key in ["WindowCenter", "WindowWidth"]:
            val = metadata[key]
            if isinstance(val, (pydicom.multival.MultiValue, list)):
                metadata[key] = float(val[0])
            elif val is not None:
                metadata[key] = float(val)

        return ImageFrame(
            pixels=pixels,
            width=pixels.shape[1],
            height=pixels.shape[0],
            bit_depth=bit_depth,
            is_grayscale=True,
            metadata=metadata,
            source_format="dicom",
            file_path=source
        )
