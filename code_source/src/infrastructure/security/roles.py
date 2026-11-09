"""Access roles of the CRM, shared by api_auth (the judge of every request) and the access list (Administration › Accès)."""

from __future__ import annotations

from enum import IntEnum
from typing import Literal, Optional, TypeGuard


class Role(IntEnum):
    """Access levels, lowest to highest: a higher level includes the lower ones."""
    READONLY = 1
    COACH = 2
    ADMIN = 3


RoleName = Literal["admin", "coach", "readonly"]
ROLE_NAMES: dict[Role, RoleName] = {Role.ADMIN: "admin", Role.COACH: "coach", Role.READONLY: "readonly"}
ROLES_BY_NAME: dict[str, Role] = {name: role for role, name in ROLE_NAMES.items()}
ADMIN: RoleName = "admin"


def is_role_name(value: object) -> TypeGuard[RoleName]:
    return value in ROLES_BY_NAME


def role_named(name: object) -> Optional[Role]:
    """The role stored under this name, or None for an unknown value."""
    return ROLES_BY_NAME.get(str(name or ""))
