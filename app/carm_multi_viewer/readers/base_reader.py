from abc import ABC, abstractmethod
from typing import Any
from ..models import ImageFrame

class BaseReader(ABC):
    """Abstract base class for all file format readers."""
    
    @abstractmethod
    def can_handle(self, source: str) -> bool:
        """Return True if this reader can handle the given source."""
        pass
    
    @abstractmethod
    def read(self, source: str, **kwargs) -> ImageFrame:
        """Read the source and return an ImageFrame object."""
        pass
