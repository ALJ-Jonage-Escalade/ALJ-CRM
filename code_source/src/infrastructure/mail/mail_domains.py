"""Whether an e-mail domain can receive mail: a DNS lookup (MX, else A / AAAA) through email-validator.

Fail-open: a lookup that times out or fails answers None ("unknown"), which never flags an address. One instance per
import preview: each domain is asked once. Used on Cloud Run only (services.members.helloasso_import): dev and tests
never reach the network.
"""

from __future__ import annotations

import logging
from typing import Optional

import dns.resolver
from email_validator import EmailUndeliverableError
from email_validator.deliverability import validate_email_deliverability

logger = logging.getLogger("alj")

LOOKUP_TIMEOUT_SECONDS = 3


class MailDomainCheck:
    """A member_data_rules.DomainCheck, with one answer per domain cached for the lifetime of the instance."""

    def __init__(self) -> None:
        self._answers: dict[str, Optional[bool]] = {}
        self._resolver = dns.resolver.Resolver()  # its own: the default resolver's timeout is shared by the process
        self._resolver.lifetime = LOOKUP_TIMEOUT_SECONDS

    def __call__(self, domain: str) -> Optional[bool]:
        key = domain.strip().lower()
        if key not in self._answers:
            self._answers[key] = self._lookup(key)
        return self._answers[key]

    def _lookup(self, domain: str) -> Optional[bool]:
        try:
            info = validate_email_deliverability(domain, domain, dns_resolver=self._resolver)
        except EmailUndeliverableError:
            return False
        except Exception as e:  # noqa: BLE001 - fail-open: any DNS or library failure is "unknown", never an issue
            logger.warning("Contrôle du domaine e-mail %s impossible : %s", domain, e)
            return None
        return None if info.get("unknown-deliverability") else True
