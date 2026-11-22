"""The e-mail templates of the Communications page: listed with their kind, saved (admin) with checks and the
variables stored as keys."""

from __future__ import annotations

from typing import Optional, TypedDict

from domain.club_emails import DEFAULT_SENDER_EMAIL, DEFAULT_SENDER_NAME
from domain.email_variables import TEMPLATE_KINDS, TemplateKind, infer_kind, needs_fixing, template_error, to_keys
from domain.errors import Conflict, InvalidRequest
from infrastructure.sqlite.email_templates import EmailTemplateRepository


class SavedTemplate(TypedDict):
    name: str
    subject: str
    body: str
    sender_email: str
    sender_name: str
    kind: TemplateKind
    is_default: bool


class ListedTemplate(SavedTemplate):
    needs_fixing: bool  # a variable it may not use, or a former spelling


def kind_of(template: dict) -> TemplateKind:  # a template row
    """The template's kind; inferred from its name when saved before kinds existed."""
    kind = template.get("kind")
    return kind if kind in TEMPLATE_KINDS else infer_kind(str(template.get("name") or ""))


def list_templates() -> list[ListedTemplate]:
    """Every template, with its kind and whether it should be edited again."""
    listed: list[ListedTemplate] = []
    for row in EmailTemplateRepository.get_email_templates():
        # Old rows may hold NULL columns
        subject, body = str(row.get("subject") or ""), str(row.get("body") or "")
        kind = kind_of(row)
        listed.append(ListedTemplate(name=str(row.get("name") or ""), subject=subject, body=body,
                                     sender_email=str(row.get("sender_email") or ""),
                                     sender_name=str(row.get("sender_name") or ""), kind=kind,
                                     is_default=bool(row.get("is_default")), needs_fixing=needs_fixing(subject, body, kind)))
    return listed


def _same_name(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def save_template(name: str, subject: str, body: str, sender_email: str = "", sender_name: str = "",
                  old_name: str = "", kind: Optional[TemplateKind] = None, is_default: Optional[bool] = None) -> SavedTemplate:
    """Creates the template, or updates the one named `old_name` (renamed to `name`). Its variables are stored as keys
    ({Prénom} → {first_name}); an unknown one or one of another kind is refused (InvalidRequest), as a name taken by
    another template (Conflict). An empty sender falls back to the club's default; no kind, to the one of its name.
    is_default: the default of its kind (the previous one loses it in the same write); not given, the template keeps
    its mark unless its kind changes."""
    if not name:
        raise InvalidRequest("Le nom du modèle est obligatoire.")
    if not subject:
        raise InvalidRequest("Le sujet du modèle est obligatoire.")
    if sender_email and ("@" not in sender_email or "." not in sender_email):
        raise InvalidRequest("L'adresse d'expédition doit être une adresse e-mail valide.")
    template_kind = kind or infer_kind(name)
    problem = template_error([subject, body], template_kind)
    if problem:
        raise InvalidRequest(problem, "invalid_variable")
    rows = EmailTemplateRepository.get_email_templates()
    # A new name must not take another template's (the save would overwrite it, or fail on a rename)
    if not (old_name and _same_name(old_name, name)):
        if any(_same_name(row["name"], name) for row in rows if row["name"] != old_name):
            raise Conflict(f"Un modèle nommé « {name} » existe déjà.", "duplicate_name")
    if is_default is None:
        current = next((row for row in rows if row["name"] == (old_name or name)), None)
        is_default = bool(current and current.get("is_default") and kind_of(current) == template_kind)

    saved = SavedTemplate(name=name, subject=to_keys(subject), body=to_keys(body),
                          sender_email=sender_email or DEFAULT_SENDER_EMAIL, sender_name=sender_name or DEFAULT_SENDER_NAME,
                          kind=template_kind, is_default=is_default)
    EmailTemplateRepository.save_email_template(old_name=old_name or None, **saved)
    return saved
