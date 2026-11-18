"""Backendy przechowywania chunków."""

from .base import Backend
from .local import LocalBackend

__all__ = ["Backend", "LocalBackend", "get_backend"]


def get_backend(name: str, **kwargs) -> Backend:
    """Fabryka backendów."""
    if name == "local":
        return LocalBackend(kwargs["root"])
    if name == "github":
        from .github import GitHubBackend

        return GitHubBackend(
            repo=kwargs["repo"],
            token=kwargs["token"],
            branch=kwargs.get("branch", "main"),
            prefix=kwargs.get("prefix", "objects"),
        )
    raise ValueError(f"unknown backend: {name}")
