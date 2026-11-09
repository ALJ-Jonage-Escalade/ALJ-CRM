"""Club keys: the rules of adding, assigning, returning and archiving a key (plans/club-keys.md).

Knows nothing about HTTP: refusals are raised as domain.errors.
"""

from __future__ import annotations

from typing import List

from infrastructure.sqlite.keys import KeyRepository, KeyRow


class KeyService:

    @staticmethod
    def list_keys() -> List[KeyRow]:
        return KeyRepository.list_keys()

    @staticmethod
    def add_key(code: str) -> KeyRow:
        return KeyRepository.add_key(code)
