from carm_multi_viewer.readers.dicom_reader import DicomReader
from carm_multi_viewer.readers.image_reader import ImageFileReader
from carm_multi_viewer.readers.video_reader import VideoReader
from carm_multi_viewer.readers.raw_reader import RawReader

def get_reader(source: str):
    """Detects the file format and returns an appropriate reader."""
    readers = [
        DicomReader(),
        ImageFileReader(),
        VideoReader(),
        # RawReader is usually a fallback given its manual requirement
    ]
    
    for reader in readers:
        if reader.can_handle(source):
            return reader
            
    # RAW fallback if extension matches
    if source.lower().endswith((".raw", ".bin")):
        return RawReader()
        
    return None

def detect_signature(file_path: str):
    """Heuristic signature detection for unknown files."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(16).hex().upper()
            
        if "FFD8" in header: return "JPEG"
        if "89504E47" in header: return "PNG"
        if "424D" in header: return "BMP"
        if "44494344" in header: return "DICOM" # DICM at 128 is handled by reader
        
        return "Unknown"
    except:
        return "Error"
