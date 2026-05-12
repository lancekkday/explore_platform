"""
Synonym Service
===============

雙向同義詞累積表。查任何一個同義詞都能找到整組。
AI 發現新同義詞時自動 append 並持久化到 JSON。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from loguru import logger

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "synonyms.json"


class SynonymService:
    def __init__(self, path: str | Path = _DEFAULT_PATH):
        self._path = Path(path)
        self._lock = threading.Lock()
        # _index: keyword(lower) → frozenset of all synonyms in its group (including itself)
        self._index: dict[str, set[str]] = {}
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        try:
            raw: dict[str, list[str]] = json.loads(self._path.read_text("utf-8"))
            for key, syns in raw.items():
                group = {key.lower()} | {s.lower() for s in syns}
                for member in group:
                    existing = self._index.get(member, set())
                    self._index[member] = existing | group
        except Exception as e:
            logger.error(f"[Synonym] Failed to load {self._path}: {e}")

    def _save(self):
        # Deduplicate groups: pick the first member as canonical key
        seen: set[frozenset[str]] = set()
        out: dict[str, list[str]] = {}
        for members in self._index.values():
            key = frozenset(members)
            if key in seen:
                continue
            seen.add(key)
            sorted_members = sorted(members)
            canonical = sorted_members[0]
            out[canonical] = sorted_members[1:]
        try:
            self._path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", "utf-8")
        except Exception as e:
            logger.error(f"[Synonym] Failed to save {self._path}: {e}")

    def get_synonyms(self, keyword: str) -> list[str]:
        """取得 keyword 的所有同義詞（不含自己）"""
        kw = keyword.lower()
        with self._lock:
            group = self._index.get(kw, set())
            return [s for s in group if s != kw]

    def add_synonyms(self, keyword: str, synonyms: list[str]):
        """新增同義詞並持久化，自動建立雙向索引"""
        with self._lock:
            kw = keyword.lower()
            new_members = {kw} | {s.lower() for s in synonyms}
            # Merge with any existing groups that overlap
            merged = set(new_members)
            for m in new_members:
                merged |= self._index.get(m, set())
            # Copy per key to avoid shared mutable reference
            frozen = frozenset(merged)
            for m in frozen:
                self._index[m] = set(frozen)
            self._save()
            logger.info(f"[Synonym] Added group: {sorted(frozen)}")

    def check_product_match(self, keyword: str, title: str, intro: str) -> str | None:
        """用同義詞比對商品 title/intro，回傳命中的同義詞或 None"""
        syns = self.get_synonyms(keyword)
        if not syns:
            return None
        text = (title + " " + intro).lower()
        for s in syns:
            if s in text:
                return s
        return None


synonym_service = SynonymService()
