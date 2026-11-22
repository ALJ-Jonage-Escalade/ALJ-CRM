"""The {…} variables of the club's e-mail templates: the single list (key stored in the database, French label shown
to users, template kinds that may use it, demo value of the previews), and the rendering of a text with values.

A token is `{…}` with no `<`, `>`, `"` or line break inside, so HTML and links in a body are never taken for one.
Tokens are matched leniently: case, accents and extra spaces do not matter, and the former spellings (aliases) of
saved templates still work. The frontend mirrors this module (frontend/src/lib/templateVariables.ts); both are
checked against the same cases, frontend/src/lib/templateVariables.golden.json.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Literal, Mapping, Optional

from domain.utils import normalize_name

TemplateKind = Literal["adherent", "attestation", "competition"]
TEMPLATE_KINDS: tuple[TemplateKind, ...] = ("adherent", "attestation", "competition")

VariableKey = Literal[
    "first_name", "last_name", "num_licence", "tarif", "season", "amount", "problemes",
    "name_competition", "no_competition", "date_competition", "montant_competition", "whatsapp_link",
]

ALL_KINDS: tuple[TemplateKind, ...] = TEMPLATE_KINDS


@dataclass(frozen=True)
class TemplateVariable:
    key: VariableKey
    label: str
    kinds: tuple[TemplateKind, ...]
    demo: str
    removes_line_when_empty: bool = False


VARIABLES: tuple[TemplateVariable, ...] = (
    TemplateVariable("first_name", "Prénom", ALL_KINDS, "Alex"),
    TemplateVariable("last_name", "Nom", ALL_KINDS, "MARTIN"),
    TemplateVariable("num_licence", "N° de licence", ALL_KINDS, "847291"),
    TemplateVariable("tarif", "Tarif", ALL_KINDS, "Cours Ados 2 (Mercredi 17h30)"),
    TemplateVariable("season", "Saison", ALL_KINDS, "2026-2027"),
    TemplateVariable("amount", "Montant de l'adhésion", ("adherent", "attestation"), "195"),
    TemplateVariable("problemes", "Problèmes à corriger", ("adherent",), "- Date de naissance manquante"),
    TemplateVariable("name_competition", "Nom de la compétition", ("competition",), "Championnat Régional Bloc"),
    TemplateVariable("no_competition", "N° de la compétition", ("competition",), "2026-RA-0142"),
    TemplateVariable("date_competition", "Date de la compétition", ("competition",), "15/11/2026"),
    TemplateVariable("montant_competition", "Montant de la compétition", ("competition",), "15,50"),
    TemplateVariable("whatsapp_link", "Lien WhatsApp", ("competition",), "https://chat.whatsapp.com/demo",
                     removes_line_when_empty=True),
)

# Former spellings found in saved templates, with the text they stand for (in keys): accepted when sending,
# rewritten on save. They can go once every template has been saved again.
WHATSAPP_SENTENCE = "Voici le lien du groupe WhatsApp dédié à cette compétition : {whatsapp_link}"
ALIASES: dict[str, str] = {
    "nom_competition": "{name_competition}",
    "whatapp_id": "{whatsapp_link}",
    "whatsapp_id": "{whatsapp_link}",
    "whatapp_link": "{whatsapp_link}",
    "bloc_whatsapp": WHATSAPP_SENTENCE,
    "bloc_whatapp": WHATSAPP_SENTENCE,
    "whatsapp_bloc": WHATSAPP_SENTENCE,
}

TOKEN = re.compile(r"\{([^{}<>\"\r\n]+)\}")


def _fold(name: str) -> str:
    return normalize_name(name)


_BY_NAME: dict[str, TemplateVariable] = {}
for _variable in VARIABLES:
    _BY_NAME[_fold(_variable.key)] = _variable
    _BY_NAME[_fold(_variable.label)] = _variable


_ALIASES_BY_NAME = {_fold(alias): text for alias, text in ALIASES.items()}


def expand_aliases(text: str) -> str:
    """The text with each former spelling replaced by the text it stands for."""
    return TOKEN.sub(lambda match: _ALIASES_BY_NAME.get(_fold(match.group(1)), match.group(0)), text)


def aliases_of(key: VariableKey) -> list[str]:
    """The former spellings standing for this variable (alone or within a sentence)."""
    return [alias for alias, text in ALIASES.items() if "{" + key + "}" in text]


def find_variable(name: str) -> Optional[TemplateVariable]:
    """The variable a token's name stands for (its key or its label, leniently), or None."""
    return _BY_NAME.get(_fold(name))


def render_template(text: Optional[str], values: Mapping[str, str], escape_html: bool = False) -> str:
    """The text with each known variable replaced by its value (an empty string when missing); unknown tokens are
    left as written. escape_html=True: values are HTML-escaped (their line breaks become <br>), for a body already
    converted to HTML: member data comes from the public HelloAsso form and must never add markup."""
    if not text:
        return ""

    def value(variable: TemplateVariable) -> str:
        return str(values.get(variable.key) or "").strip()

    def is_dropped(line: str) -> bool:
        """A line showing a variable that removes its line when empty (the WhatsApp link)."""
        for match in TOKEN.finditer(line):
            variable = find_variable(match.group(1))
            if variable is not None and variable.removes_line_when_empty and not value(variable):
                return True
        return False

    def value_of(match: re.Match[str]) -> str:
        variable = find_variable(match.group(1))
        if variable is None:
            return match.group(0)
        filled = value(variable)
        return html.escape(filled).replace("\n", "<br>\n") if escape_html else filled

    lines = re.split(r"(?<=\n)", expand_aliases(str(text)))
    kept_lines = [line for line in lines if not is_dropped(line)]
    kept = "".join(kept_lines)
    if len(kept_lines) != len(lines):
        kept = re.sub(r"\n{3,}", "\n\n", kept)
    return TOKEN.sub(value_of, kept)


def _rewrite(text: str, show: Callable[[TemplateVariable], str]) -> str:
    """The text with its former spellings expanded and each known token written as show(variable)."""
    def rewrite(match: re.Match[str]) -> str:
        variable = find_variable(match.group(1))
        return match.group(0) if variable is None else "{" + show(variable) + "}"

    return TOKEN.sub(rewrite, expand_aliases(text or ""))


def to_keys(text: str) -> str:
    """The text as stored: each variable written with its key ({first_name}), whatever the spelling typed."""
    return _rewrite(text, lambda variable: variable.key)


def to_labels(text: str) -> str:
    """The text as users read it: each variable written with its French label ({Prénom})."""
    return _rewrite(text, lambda variable: variable.label)


KIND_LABELS: dict[TemplateKind, str] = {"adherent": "Adhérent", "attestation": "Attestation", "competition": "Compétition"}


def infer_kind(name: str) -> TemplateKind:
    """The kind of a template saved before kinds existed, from its name (the rules the screens used to pick one)."""
    folded = _fold(name)
    if "competition" in folded:
        return "competition"
    if "attestation" in folded or "echeance" in folded:
        return "attestation"
    return "adherent"


def _variables_in(name: str) -> Optional[list[TemplateVariable]]:
    """The variables a token stands for (several for a former sentence), or None when it is no variable."""
    expansion = _ALIASES_BY_NAME.get(_fold(name))
    if expansion is None:
        variable = find_variable(name)
        return None if variable is None else [variable]
    return [variable for match in TOKEN.finditer(expansion) if (variable := find_variable(match.group(1))) is not None]


def _listed(tokens: list[str], one: str, many: str) -> str:
    return f"{one if len(tokens) == 1 else many} : {', '.join(tokens)}."


def template_error(texts: Iterable[str], kind: Optional[TemplateKind] = None) -> Optional[str]:
    """Why a template whose subject and body are `texts` cannot be saved (None: it can): the tokens that are no
    variable, those of another kind, then the valid ones. `kind`: only the variables of this template kind are valid."""
    unknown: list[str] = []
    other_kind: list[str] = []
    for text in texts:
        for match in TOKEN.finditer(text or ""):
            token = match.group(0)
            variables = _variables_in(match.group(1))
            if variables is None:
                if token not in unknown:
                    unknown.append(token)
            elif kind is not None and any(kind not in variable.kinds for variable in variables) and token not in other_kind:
                other_kind.append(token)
    if not unknown and not other_kind:
        return None
    parts = []
    if unknown:
        parts.append(_listed(unknown, "Variable inconnue", "Variables inconnues"))
    if other_kind and kind is not None:
        label = KIND_LABELS[kind]
        parts.append(_listed(other_kind, f"Variable non disponible pour un modèle {label}",
                             f"Variables non disponibles pour un modèle {label}"))
    valid = ", ".join("{" + variable.label + "}" for variable in VARIABLES if kind is None or kind in variable.kinds)
    return f"{' '.join(parts)} Variables possibles : {valid}."


def needs_fixing(subject: str, body: str, kind: TemplateKind) -> bool:
    """Whether a saved template should be edited again: a variable it may not use, or one not written with its key
    (a former spelling, still sent correctly until the template is saved again)."""
    return template_error([subject, body], kind) is not None or to_keys(subject) != subject or to_keys(body) != body
