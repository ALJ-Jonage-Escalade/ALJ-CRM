import csv
import datetime
import io
import logging
import os
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from domain.communications.club_emails import CLUB_CONTACT_EMAIL
from domain.members.countries import FRANCE_CODE, parse_country
from domain.members.sex import parse_sex
from domain.members.view import is_cancelled
from domain.utils import clean_digits_only, is_missing
from exports.spreadsheet_safety import csv_safe

logger = logging.getLogger("alj")

def parse_date_to_datetime(val):
    if not val or is_missing(val):
        return ""
    if isinstance(val, (datetime.datetime, datetime.date)):
        if isinstance(val, datetime.date) and not isinstance(val, datetime.datetime):
            return datetime.datetime(val.year, val.month, val.day)
        return val
        
    val_str = str(val).strip()
    if not val_str:
        return ""
        
    # Essayer de parser différents formats de chaînes courants
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%y", "%Y-%m-%d %H:%M:%S"):
        try:
            # Pour l'ISO-8601 complet (avec millisecondes et décalage)
            if "T" in val_str and fmt == "%Y-%m-%dT%H:%M:%S":
                return datetime.datetime.strptime(val_str[:19], fmt)
            return datetime.datetime.strptime(val_str, fmt)
        except ValueError:
            pass
            
    # Si on n'a pas réussi à parser mais que c'est une chaîne non vide, on la renvoie brute
    return val_str


FFME_CSV_HEADERS = [
    "numero de licence", "nom", "prenom", "date de naissance", "sexe", "nationalite",
    "adresse", "adresse complement", "code postal", "ville", "pays", "tel fixe", "tel mobile",
    "courriel", "courriel 2", "pap nom", "pap prenom", "pap telephone", "pap courriel",
    "nom de naissance", "commune de naissance", "departement de naissance", "type licence",
    "assurance", "option ski", "option slackline", "option trail", "option vtt",
    "assurance complementaire", "option protection agression"
]


def ffme_csv_bytes(participants_data, include_termine: bool = False) -> bytes:
    """The FFME import CSV (strict format: « ; » separator, dd/mm/yyyy dates), built in memory.
    With include_termine, members whose status is 'Terminé' are included too."""
    return _render_ffme_csv(_ffme_csv_rows(participants_data, include_termine)[0])


def generate_ffme_csv(participants_data, output_path: str, include_termine: bool = False):
    """Writes the FFME import CSV (see ffme_csv_bytes) to `output_path`; returns the members left out, with the reason."""
    csv_rows, ignored_members, _to_check = _ffme_csv_rows(participants_data, include_termine)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(_render_ffme_csv(csv_rows))
    return ignored_members


def _render_ffme_csv(csv_rows: list[list[str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(FFME_CSV_HEADERS)
    # Member data must never be evaluated as a formula when the file is opened
    writer.writerows([[csv_safe(v) for v in row] for row in csv_rows])
    return buffer.getvalue().encode("utf-8")


# Birth dates after this day get a youth licence ("J"), the others an adult one ("A")
YOUTH_BIRTH_DATE_CUTOFF = datetime.datetime(2009, 8, 31)
_YES_VALUES = ("OUI", "TRUE", "VRAI")


def _is_yes(value: object) -> bool:
    return str(value).upper() in _YES_VALUES


@dataclass(frozen=True)
class FfmeRowCheck:
    """A member to declare in the FFME CSV: their row, or why they are left out; and what the office should check
    on a row that is exported anyway (a value exported empty)."""
    label: str  # "POTTER Harry"
    order_ref: str
    row: list[str] | None  # None: left out
    left_out_reason: str = ""
    to_check: list[str] = field(default_factory=list)

    @property
    def is_renewal(self) -> bool:
        return bool(self.row and self.row[0])


def check_ffme_member(member: Mapping[str, object], include_termine: bool) -> FfmeRowCheck | None:
    """The FFME CSV row of a member read from the database, None when the member is not declared (waiting list,
    nothing paid, cancelled, 'Terminé' unless include_termine). Shared by the export and its statistics."""
    # None values of the member read model become empty strings first: otherwise str(None) would give
    # 'NO' (country), 'none' (second e-mail), 'NONE' (emergency contact), 'None' (address, city)
    member = {k: (v if v is not None else "") for k, v in member.items()}
    if not _is_declared(member, include_termine):
        return None
    return _ffme_row(member)


def _ffme_csv_rows(participants_data: Iterable[Mapping[str, object]], include_termine: bool) -> tuple[list[list[str]], list[str], list[str]]:
    """The CSV rows of the members to declare, sorted by name, a line per member left out (missing birth date or sex,
    unknown country or nationality on a first licence) and a line per value to check (exported empty)."""
    csv_rows: list[list[str]] = []
    ignored_members: list[str] = []
    to_check: list[str] = []
    for member in participants_data:
        check = check_ffme_member(member, include_termine)
        if check is None:
            continue
        who = f"{check.label} (Commande {check.order_ref})"
        if check.row is None:
            ignored_members.append(f"⚠️ [IGNORÉ] {who} : {check.left_out_reason}")
            continue
        csv_rows.append(check.row)
        to_check.extend(f"⚠️ [À VÉRIFIER] {who} : {item}" for item in check.to_check)
    # The file's own order, whatever the order of the member rows read: by name, then birth date and licence
    csv_rows.sort(key=_ffme_row_order)
    return csv_rows, ignored_members, to_check


def _ffme_row_order(row: list[str]) -> tuple[str, str, str, str]:
    licence, last_name, first_name, birth_date = row[:4]
    day, month, year = birth_date.split("/")
    return last_name, first_name, f"{year}{month}{day}", licence


def _is_declared(member: dict, include_termine: bool) -> bool:
    """False for the waiting lists, nothing paid (unless added by hand), cancelled orders, and members already
    declared ('Terminé') unless asked for."""
    tarif_name = str(member.get("tarif_name", "")).lower()
    status = str(member.get("status", "")).lower()
    added_by_hand = "ajout manuel" in str(member.get("commentaires_correctif", "")).lower()
    if "attente" in tarif_name or (member.get("amount", 0.0) == 0.0 and not added_by_hand) or is_cancelled(status):
        return False
    return include_termine or not is_termine(member)


def is_termine(member: Mapping[str, object]) -> bool:
    """Status 'Terminé': the membership is already declared to the FFME."""
    return "termin" in str(member.get("status") or "").lower()


def _ffme_row(member: dict) -> FfmeRowCheck:
    """The CSV row of a member to declare, or why they are left out."""
    last_name = str(member.get("last_name", "")).strip().upper() or "INCONNU"
    first_name = str(member.get("first_name", "")).strip() or "INCONNU"
    label, order_ref = f"{last_name} {first_name}", str(member.get("order_ref", ""))

    def left_out(reason: str) -> FfmeRowCheck:
        return FfmeRowCheck(label, order_ref, None, left_out_reason=reason)

    licence = clean_digits_only(member.get("licence_ffme", ""))
    if not 5 <= len(licence) <= 10:
        licence = ""

    raw_birth_date = member.get("birth_date", "")
    birth_date = parse_date_to_datetime(raw_birth_date if isinstance(raw_birth_date, datetime.date) else str(raw_birth_date).strip())
    if not isinstance(birth_date, datetime.datetime) or birth_date >= datetime.datetime.now():
        return left_out(f"date de naissance absente ou invalide ('{raw_birth_date}')")

    # Sex: required for a first licence (never guessed), may be empty for a renewal
    sex = parse_sex(member.get("sex"))
    if sex is None and not licence:
        return left_out("sexe non renseigné")

    # Country and nationality: ISO codes, France when not given; a value not recognised is never guessed
    country, country_problem = _ffme_country_code(member.get("country", ""), "pays non reconnu")
    nationality, nationality_problem = _ffme_country_code(member.get("nationality", ""), "nationalité non reconnue")
    problems = [problem for problem in (country_problem, nationality_problem) if problem]
    if problems and not licence:  # the FFME needs both to create a licence
        return left_out(", ".join(problems))
    to_check = [f"{problem} → champ vide dans le fichier" for problem in problems]

    # A first licence needs an address: the club's when the member gave none
    address = str(member.get("address", "")).strip()[:255]
    if not address and not licence:
        address = "ADRESSE NON COMMUNIQUEE"

    zip_code = clean_digits_only(member.get("zip_code", ""))
    if country == FRANCE_CODE:
        if zip_code:
            zip_code = zip_code.zfill(5)[:5]
        else:
            zip_code = "69330" if not licence else ""
    else:
        zip_code = zip_code[:10]

    city = str(member.get("city", "")).strip().upper()[:100]
    if not city and not licence:
        city = "JONAGE"

    phone = clean_digits_only(member.get("phone", ""))
    if country == FRANCE_CODE and phone:
        if phone.startswith("33"):
            phone = "0" + phone[2:]
        phone = phone[:10]

    email = str(member.get("email_primary", "")).strip().lower()[:100]
    if not email:
        email = str(member.get("payer_email", "")).strip().lower()[:100]
    if not email and not licence:
        email = CLUB_CONTACT_EMAIL
    second_email = str(member.get("email_secondary", "")).strip().lower()[:100]

    # Emergency contact ("PAP"): "First Last", or a single last name
    emergency_name = str(member.get("emergency1_name", "")).strip()
    emergency_last_name = emergency_first_name = ""
    if " " in emergency_name:
        first, last = emergency_name.split(" ", 1)
        emergency_first_name, emergency_last_name = first[:100], last.upper()[:100]
    elif emergency_name:
        emergency_last_name = emergency_name.upper()[:100]
    emergency_phone = clean_digits_only(member.get("emergency1_phone", ""))[:15]

    if str(member.get("is_tribe", "")).lower() in ("true", "vrai", "oui", "1"):
        licence_type = "F"
    else:
        licence_type = "J" if birth_date > YOUTH_BIRTH_DATE_CUTOFF else "A"

    if _is_yes(member.get("opt_Assurance Base ++", "Non")):
        insurance = "B++"
    elif _is_yes(member.get("opt_Assurance Base +", "Non")):
        insurance = "B+"
    elif _is_yes(member.get("opt_Assurance Base", "Non")):
        insurance = "B"
    else:
        insurance = "RC"

    def option(key: str) -> str:
        return "OUI" if _is_yes(member.get(key, "Non")) else "NON"

    row = [
        licence, last_name, first_name, birth_date.strftime("%d/%m/%Y"), sex.value if sex else "", nationality, address, "",
        zip_code, city, country, "", phone, email, second_email, emergency_last_name, emergency_first_name, emergency_phone,
        "", "", "", "", licence_type, insurance, option("opt_Assurance Option ski de piste"), "NON",
        option("opt_Assurance Option Trail"), option("opt_Assurance Option VTT"), "NON", "NON",
    ]
    return FfmeRowCheck(label, order_ref, row, to_check=to_check)


def _ffme_country_code(raw: object, unknown: str) -> tuple[str, str]:
    """The ISO code of a stored country or nationality ("FR" when empty), or "" and the problem when not recognised."""
    text = str(raw).strip()
    if not text:
        return FRANCE_CODE, ""
    country = parse_country(text)
    if country is None:
        return "", f"{unknown} ('{text}')"
    return country.code, ""
