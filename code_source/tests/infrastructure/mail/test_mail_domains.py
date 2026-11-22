"""E-mail domain check: deliverable, undeliverable, unknown (fail-open), one lookup per domain. DNS is patched out."""

from unittest.mock import patch

import dns.exception
import pytest
from email_validator import EmailUndeliverableError

from infrastructure.mail.mail_domains import MailDomainCheck

LOOKUP = "infrastructure.mail.mail_domains.validate_email_deliverability"


@pytest.mark.parametrize(("lookup", "expected"), [
    pytest.param({"return_value": {"mx": [(10, "mx.example.org")]}}, True, id="deliverable"),
    pytest.param({"return_value": {"unknown-deliverability": "timeout"}}, None, id="unknown-deliverability"),
    pytest.param({"side_effect": EmailUndeliverableError("no MX")}, False, id="undeliverable"),
    pytest.param({"side_effect": dns.exception.Timeout()}, None, id="dns-failure-is-unknown"),
])
def test_domain_check_answer(lookup, expected):
    with patch(LOOKUP, **lookup):
        assert MailDomainCheck()("example.org") is expected


def test_domain_check_looks_each_domain_up_once_case_and_spaces_ignored():
    check = MailDomainCheck()
    with patch(LOOKUP, return_value={}) as lookup:
        assert check("Example.org") is True
        assert check(" example.ORG ") is True
    lookup.assert_called_once()
    assert lookup.call_args.args[:2] == ("example.org", "example.org")
