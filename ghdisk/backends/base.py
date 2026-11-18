"""Interfejs backendu przechowywania."""

from abc import ABC, abstractmethod


class Backend(ABC):
    """Magazyn blobów adresowanych po SHA-256."""

    @abstractmethod
    def put(self, sha: str, blob: bytes) -> None:
        """Zapisuje blob (może być buforowany do flush())."""

    @abstractmethod
    def get(self, sha: str) -> bytes:
        """Odczytuje blob; podnosi KeyError gdy brak."""

    @abstractmethod
    def delete(self, sha: str) -> None:
        """Usuwa blob (może być buforowane do flush())."""

    @abstractmethod
    def exists(self, sha: str) -> bool:
        """Czy blob istnieje w magazynie."""

    def flush(self) -> int:
        """Wypycha bufor do magazynu. Zwraca liczbę zapisanych obiektów."""
        return 0

    def close(self) -> None:
        """Zwalnia zasoby."""
        self.flush()
