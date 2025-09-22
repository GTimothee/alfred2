from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseCrawler(ABC):
    @abstractmethod
    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch and return a list of entries."""
        pass

    @abstractmethod
    def save(self, data: List[Dict[str, Any]], output_filepath: str) -> None:
        """Save the fetched data to a file."""
        pass

    @abstractmethod
    def load(self, input_filepath: str) -> List[Dict[str, Any]]:
        """Load data from a file."""
        pass