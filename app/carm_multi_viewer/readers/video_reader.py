import cv2
import numpy as np
from carm_multi_viewer.readers.base_reader import BaseReader
from carm_multi_viewer.models import ImageFrame

class VideoReader(BaseReader):
    """Reader for video files like AVI, MP4, MOV (Cine loops)."""
    
    SUPPORTED = (".avi", ".mp4", ".mov", ".mkv")
    
    def can_handle(self, source: str) -> bool:
        return source.lower().endswith(self.SUPPORTED)

    def read(self, source: str, **kwargs) -> ImageFrame:
        """Reads the FIRST frame of the video and returns metadata for the loop."""
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {source}")
            
        ret, frame = cap.read()
        if not ret:
            cap.release()
            raise ValueError(f"Unable to read first frame of video: {source}")
            
        # Get metadata
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Convert first frame to grayscale
        if len(frame.shape) == 3:
            pixels = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            pixels = frame
            
        cap.release()
        
        return ImageFrame(
            pixels=pixels,
            width=width,
            height=height,
            bit_depth=8, # Videos are typically 8-bit per channel
            is_grayscale=True,
            metadata={
                "FPS": fps,
                "FrameCount": frame_count,
                "IsVideo": True
            },
            source_format="video",
            file_path=source
        )

    def get_capture(self, source: str):
        """Returns a VideoCapture object for the GUI to use for playback."""
        return cv2.VideoCapture(source)
