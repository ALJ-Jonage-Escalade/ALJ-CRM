"""Checks of a member's data at the HelloAsso membership import (plans/helloasso-import-data-checks.md). Pure, no I/O.

One entry point, check_member_data: the values as they will be stored come back normalised, with their issues. Only
a birth-date issue blocks (the registration then waits in « À vérifier »); every other one is a warning.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Optional, TypeGuard, get_args

import phonenumbers
from email_validator import EmailNotValidError, validate_email

from domain.members.countries import parse_country

# Plausible age on the season start (1 September): below, the registration year was typed in; above, a typo such as
# 1026. Plain constants, not the group age rules.
MIN_AGE = 3
MAX_AGE = 100

# Whether a domain can receive mail: True, False, or None when the check could not answer (never an issue)
DomainCheck = Callable[[str], Optional[bool]]

IssueField = Literal["birth_date", "phone", "emergency_phone_1", "emergency_phone_2", "email", "email_2", "country",
                     "nationality", "licence"]


def is_issue_field(value: object) -> TypeGuard[IssueField]:
    return value in get_args(IssueField)


@dataclass(frozen=True)
class DataIssue:
    field: IssueField
    code: str  # stable, read by the tests and the frontend
    message: str  # French, shown to the admin
    blocking: bool = False


@dataclass(frozen=True)
class MemberValues:
    birth_date: str = ""  # as typed (dd/mm/yyyy) or ISO; normalised: ISO, "" when blocking
    # Normalised: French numbers "06 12 34 56 78", foreign ones international ("+41 79 123 45 67"); as typed when invalid
    phone: str = ""
    emergency_phone_1: str = ""
    emergency_phone_2: str = ""
    # Normalised by email-validator (domain lower-cased); as typed when invalid
    email: str = ""
    email_2: str = ""
    # Normalised: the canonical name / nationality of the country table (countries.py); as typed when not recognised
    country: str = ""
    nationality: str = ""
    licence: str = ""  # FFME licence; normalised: its digits ("" when it has none: no licence)


@dataclass(frozen=True)
class CheckedValues:
    values: MemberValues  # normalised
    issues: tuple[DataIssue, ...] = ()


def season_start(season: str) -> datetime.date:
    """1 September of the season's first year ("2026-2027" → 2026-09-01). ValueError for another text."""
    return datetime.date(int(season.split("-", 1)[0]), 9, 1)


def read_birth_date(raw: str) -> datetime.date | None:
    """A birth date as typed on the form (dd/mm/yyyy) or as HelloAsso sends date fields (ISO, with or without a time).
    None when it cannot be read: two-digit years and other formats are never guessed."""
    text = str(raw or "").strip()
    for date_format, value in (("%d/%m/%Y", text), ("%Y-%m-%d", text.split("T", 1)[0])):
        try:
            return datetime.datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def _age_on(birth: datetime.date, day: datetime.date) -> int:
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def _birth_date(raw: str, season_start: datetime.date) -> tuple[str, list[DataIssue]]:
    typed = str(raw or "").strip()
    if not typed:
        return "", [DataIssue("birth_date", "missing", "Date de naissance manquante.", blocking=True)]
    birth = read_birth_date(typed)
    if birth is None:
        return "", [DataIssue("birth_date", "unreadable", f"Date de naissance illisible (« {typed} ») : format attendu jj/mm/aaaa.",
                              blocking=True)]
    shown = birth.strftime("%d/%m/%Y")
    if birth > datetime.date.today():
        return "", [DataIssue("birth_date", "future", f"Date de naissance dans le futur ({shown}).", blocking=True)]
    age = _age_on(birth, season_start)
    if age < MIN_AGE:
        return "", [DataIssue("birth_date", "too_young", f"Date de naissance invraisemblable ({shown}) : moins de {MIN_AGE} ans "
                                                         "au début de la saison.", blocking=True)]
    if age > MAX_AGE:
        return "", [DataIssue("birth_date", "too_old", f"Date de naissance invraisemblable ({shown}) : plus de {MAX_AGE} ans "
                                                       "au début de la saison.", blocking=True)]
    return birth.isoformat(), []


_PHONE_LABELS: dict[IssueField, str] = {"phone": "Téléphone de l'adhérent", "emergency_phone_1": "Téléphone du contact d'urgence",
                                         "emergency_phone_2": "Téléphone du 2e contact d'urgence"}


def _phone(field: IssueField, raw: str, required: bool) -> tuple[str, list[DataIssue]]:
    """A phone number, region FR by default: valid ones reformatted (national for France, international otherwise)."""
    typed = str(raw or "").strip()
    label = _PHONE_LABELS[field]
    if not typed:
        return "", [DataIssue(field, "missing", f"{label} manquant.")] if required else []
    try:
        number = phonenumbers.parse(typed, "FR")
    except phonenumbers.NumberParseException:
        number = None
    if number is None or not phonenumbers.is_valid_number(number):
        return typed, [DataIssue(field, "invalid", f"{label} invalide (« {typed} »).")]
    french = phonenumbers.region_code_for_number(number) == "FR"
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.NATIONAL if french
                                      else phonenumbers.PhoneNumberFormat.INTERNATIONAL), []


_EMAIL_LABELS: dict[IssueField, str] = {"email": "Adresse e-mail du club", "email_2": "Deuxième adresse e-mail du club"}


def _email(field: IssueField, raw: str, required: bool, domain_accepts_mail: Optional[DomainCheck]) -> tuple[str, list[DataIssue]]:
    """An e-mail address: syntax and normalisation by email-validator, then whether its domain can receive mail."""
    typed = str(raw or "").strip()
    label = _EMAIL_LABELS[field]
    if not typed:
        return "", [DataIssue(field, "missing", f"{label} manquante.")] if required else []
    try:
        address = validate_email(typed, check_deliverability=False)
    except EmailNotValidError:
        return typed, [DataIssue(field, "invalid", f"{label} invalide (« {typed} »).")]
    if domain_accepts_mail is not None and domain_accepts_mail(address.ascii_domain) is False:
        return address.normalized, [DataIssue(field, "no_mail_domain", f"{label} : le domaine « {address.domain} » ne reçoit pas "
                                                                       f"d'e-mails (faute de frappe ?).")]
    return address.normalized, []


def _country(field: IssueField, raw: str) -> tuple[str, list[DataIssue]]:
    """A country or nationality typed in any recognised spelling ("FRANCAISE", "fr"), stored in the canonical one."""
    typed = str(raw or "").strip()
    label = "Pays" if field == "country" else "Nationalité"
    if not typed:
        return "", [DataIssue(field, "missing", f"{label} manquant{'e' if field == 'nationality' else ''}.")]
    country = parse_country(typed)
    if country is None:
        return typed, [DataIssue(field, "unknown", f"{label} non reconnu{'e' if field == 'nationality' else ''} (« {typed} »).")]
    return (country.name if field == "country" else country.nationality), []


LICENCE_DIGITS = (6, 7)  # the FFME numbers have 6 or 7 digits


def _licence(raw: str) -> tuple[str, list[DataIssue]]:
    """An FFME licence: its digits, six or seven. Text without digit ("non", "en cours") is no licence."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits and len(digits) not in LICENCE_DIGITS:
        return digits, [DataIssue("licence", "invalid", f"Licence FFME invalide (« {str(raw).strip()} ») : 6 ou 7 chiffres attendus.")]
    return digits, []


def check_member_data(values: MemberValues, *, season_start: datetime.date,
                      domain_accepts_mail: Optional[DomainCheck] = None) -> CheckedValues:
    """The values normalised, and their issues. `domain_accepts_mail`: None skips the domain check (dev, tests)."""
    checked = {
        "birth_date": _birth_date(values.birth_date, season_start),
        "phone": _phone("phone", values.phone, required=True),
        "emergency_phone_1": _phone("emergency_phone_1", values.emergency_phone_1, required=False),
        "emergency_phone_2": _phone("emergency_phone_2", values.emergency_phone_2, required=False),
        "email": _email("email", values.email, True, domain_accepts_mail),
        "email_2": _email("email_2", values.email_2, False, domain_accepts_mail),
        "country": _country("country", values.country),
        "nationality": _country("nationality", values.nationality),
        "licence": _licence(values.licence),
    }
    normalised = MemberValues(**{field: value for field, (value, _issues) in checked.items()})
    return CheckedValues(normalised, tuple(issue for _value, issues in checked.values() for issue in issues))
