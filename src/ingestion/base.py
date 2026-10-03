"""Shared adapter interface. Every source adapter supports replay (cached file) and
live (network) modes and yields normalised Document objects."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from src.ingestion.schema import Document


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    def fetch_live(self, **kwargs) -> Iterator[Document]:
        """Hit the real network source. Must raise cleanly on failure, never hang."""
        raise NotImplementedError

    def fetch_replay(self, cache_path: Path) -> Iterator[Document]:
        """Read previously cached JSONL. Deterministic, offline, used by --demo mode."""
        if not cache_path.exists():
            return iter(())
        return self._read_jsonl(cache_path)

    @staticmethod
    def _read_jsonl(path: Path) -> Iterator[Document]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield Document.model_validate_json(line)

    @staticmethod
    def write_jsonl(docs: list[Document], path: Path) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with path.open("w", encoding="utf-8") as f:
            for d in docs:
                f.write(d.model_dump_json() + "\n")
                n += 1
        return n

    @staticmethod
    def append_jsonl(docs: list[Document], path: Path) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with path.open("a", encoding="utf-8") as f:
            for d in docs:
                f.write(d.model_dump_json() + "\n")
                n += 1
        return n
