"""First admin of a fresh project: the address set once on the Cloud Run service (`BOOTSTRAP_ADMIN_EMAIL`).

At startup, when that address is not in the access list, it is added as admin. Created only if absent (Firestore
`create`): several instances starting together create it once, and an existing entry (a role changed on the page) is
never overwritten. Skipped in dev mode (the emulator only holds the seeded data). Never blocks startup.
"""

from __future__ import annotations

import logging

from infrastructure import runtime_env
from infrastructure.firestore.access_store import AccessStore, HistoryEntry, RoleEntry
from infrastructure.security.role_directory import Clock, RoleDirectory
from services.access.rules import BOOTSTRAP_AUTHOR, checked_email, iso
from services.errors import InvalidRequest

logger = logging.getLogger("alj")


def bootstrap_admin(store: AccessStore, clock: Clock, email: str) -> bool:
    """Adds `email` as admin unless it is listed; True when the entry was created. Raises on a store error."""
    address = checked_email(email)
    at = iso(clock())
    created = store.create_role(RoleEntry(
        email=address, role="admin", display_name="", last_sign_in_at=None,
        created_at=at, created_by=BOOTSTRAP_AUTHOR, updated_at=at, updated_by=BOOTSTRAP_AUTHOR))
    if created:
        store.add_history(HistoryEntry(at=at, author=BOOTSTRAP_AUTHOR, action="bootstrap", target_email=address,
                                       old_role=None, new_role="admin"))
    return created


def run_at_startup(directory: RoleDirectory) -> None:
    """Startup step of the server: logs, never raises."""
    if runtime_env.is_dev():
        logger.info("Bootstrap admin skipped in dev mode (emulator: seeded access list)")
        return
    email = directory.bootstrap_email
    if not email:
        logger.warning("BOOTSTRAP_ADMIN_EMAIL is not set: no emergency admin access on this service "
                       "(see the Cloud Run setup guide)")
        return
    try:
        if bootstrap_admin(directory.store, directory.clock, email):
            logger.info("Bootstrap admin added to the access list")
            directory.invalidate()
    except InvalidRequest as e:
        logger.warning("BOOTSTRAP_ADMIN_EMAIL ignored: %s", e.message)
    except Exception:
        logger.exception("Bootstrap admin: the access list could not be updated")
