"""版本化、按业务域隔离并带歧义保护的 Query 别名扩展。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AliasExpansion:
    original_query: str
    expanded_query: str
    version: str
    domain: str
    applied: tuple[str, ...]
    blocked_ambiguous: tuple[str, ...]


class AliasRegistry:
    def __init__(self, payload: dict[str, Any]):
        self.version = str(payload.get("version") or "").strip()
        if not self.version:
            raise ValueError("alias registry version 不能为空")
        self.domains = payload.get("domains") or {}
        if not isinstance(self.domains, dict):
            raise ValueError("alias registry domains 必须是 object")
        self.fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self._validate()

    @classmethod
    def load(cls, path: str | Path) -> "AliasRegistry":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def _validate(self) -> None:
        for domain, config in self.domains.items():
            entries = config.get("entries") or []
            ambiguous = {str(value).casefold() for value in config.get("ambiguous_aliases") or []}
            seen: dict[str, str] = {}
            for entry in entries:
                canonical = str(entry.get("canonical") or "").strip()
                aliases = [str(value).strip() for value in entry.get("aliases") or []]
                if not canonical or not aliases:
                    raise ValueError(f"{domain} alias entry 缺 canonical/aliases")
                for alias in aliases:
                    key = alias.casefold()
                    if key in ambiguous:
                        continue
                    previous = seen.setdefault(key, canonical)
                    if previous != canonical:
                        raise ValueError(f"{domain} alias 歧义未声明:{alias}")

    def expand(self, query: str, *, domain: str, max_terms: int = 4) -> AliasExpansion:
        config = self.domains.get(domain) or {}
        ambiguous = {str(value).casefold() for value in config.get("ambiguous_aliases") or []}
        lowered = query.casefold()
        applied: list[str] = []
        blocked: list[str] = []
        additions: list[str] = []
        for entry in config.get("entries") or []:
            canonical = str(entry["canonical"]).strip()
            aliases = [str(value).strip() for value in entry.get("aliases") or []]
            matched = canonical.casefold() in lowered or any(alias.casefold() in lowered for alias in aliases)
            if not matched:
                continue
            for alias in aliases:
                if alias.casefold() in ambiguous:
                    blocked.append(alias)
                    continue
                if alias.casefold() not in lowered and alias not in additions:
                    additions.append(alias)
            applied.append(canonical)
        additions = additions[:max_terms]
        expanded = query if not additions else f"{query} {' '.join(additions)}"
        return AliasExpansion(
            original_query=query,
            expanded_query=expanded,
            version=self.version,
            domain=domain,
            applied=tuple(applied),
            blocked_ambiguous=tuple(sorted(set(blocked))),
        )
