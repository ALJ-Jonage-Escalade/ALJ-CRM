"""A MyFFME licensee export matching the seed, to try Outils › Import FFME by hand: one row per case of the preview.

Called by seed_emulator.py on the seed SQLite database, before it is pushed to the emulator:
1. `extra_records`: two adult members the import needs (adults never race: the competition seed stays the same),
   a homonym of Harry Potter without licence and a member whose registration was cancelled;
2. `prepare_cases`: stored passports, diplomas and health documents on a few members (an empty cell keeps them);
3. `write_ffme_file`: the export (title row, then the MyFFME header), and the expected result of each case.
"""
from __future__ import annotations

import datetime
import os
from typing import Callable, Dict, List, Optional, TypedDict

import openpyxl

from domain.members.view import is_cancelled, normalize_status
from infrastructure.sqlite.connection import SqliteDatabase

FILE_NAME = "ffme_licencies_dev.xlsx"
HEADER = ["Nom", "Prénom", "N° de licence", "Date de naissance", "Passeports", "Diplômes", "Document de santé"]
HOMONYM_BIRTH = datetime.date(1980, 7, 31)
CANCELLED_LICENCE = "512345"
KEPT_PASSPORTS, KEPT_DIPLOMAS, KEPT_DOCUMENT = "Passeport Vert", "Initiateur SAE", "Certificat médical"


class SeedMember(TypedDict):
    user_id: int
    purchase_id: int
    last_name: str
    first_name: str
    licence: str
    birth_date: Optional[datetime.date]
    status: str


def extra_records(build_record: Callable[[dict, int], dict], planning: List[dict]) -> List[dict]:
    """HelloAsso records of the two extra adults (`build_record(person, order_no)`: seed_emulator.member_record)."""
    adults = next(group for group in planning if group["type"] == "cours" and not group["naissance_min"])
    homonym = build_record({"first": "Harry", "last": "Potter", "sex": "M", "birth": HOMONYM_BIRTH, "group": adults,
                            "minor": False}, 901)
    homonym.update({"status": "Validé", "champ_Numéro de Licence FFME (6 chiffres)": ""})
    cancelled = build_record({"first": "Quirinus", "last": "Quirrell", "sex": "M", "birth": datetime.date(1971, 9, 1),
                              "group": adults, "minor": False}, 902)
    cancelled.update({"status": "Annulé", "champ_Numéro de Licence FFME (6 chiffres)": CANCELLED_LICENCE})
    return [homonym, cancelled]


def _members(season: str) -> List[SeedMember]:
    conn = SqliteDatabase.get_connection()
    try:
        rows = conn.execute("""
            SELECT u.id AS user_id, p.id AS purchase_id, u.last_name, u.first_name, COALESCE(u.licence_ffme, '') AS licence,
                   u.birth_date, COALESCE(p.status, '') AS status
            FROM users u JOIN purchases p ON p.user_id = u.id JOIN orders o ON o.id = p.order_id
            JOIN seasons s ON s.id = o.season_id
            WHERE s.name = ? ORDER BY u.last_name, u.first_name, u.birth_date
        """, (season,)).fetchall()
    finally:
        conn.close()
    return [SeedMember(user_id=row["user_id"], purchase_id=row["purchase_id"], last_name=row["last_name"],
                       first_name=row["first_name"], licence=row["licence"],
                       birth_date=datetime.date.fromisoformat(row["birth_date"]) if row["birth_date"] else None,
                       status=row["status"])
            for row in rows]


def _licensed(members: List[SeedMember]) -> List[SeedMember]:
    """Licensed, registered and alone with their name: matched by licence, nothing to change by default."""
    names = [(m["last_name"], m["first_name"]) for m in members]
    return [m for m in members if m["licence"] and not is_cancelled(m["status"])
            and names.count((m["last_name"], m["first_name"])) == 1]


def _kept_member(members: List[SeedMember]) -> SeedMember:
    """Not the first nor the last member: the e2e tests change those."""
    return [m for m in _licensed(members) if normalize_status(m["status"]) == "Terminé"][1]


def prepare_cases(season: str) -> None:
    """Stored values the file leaves empty: the preview must show no change for this member."""
    kept = _kept_member(_members(season))
    conn = SqliteDatabase.get_connection()
    try:
        conn.execute("UPDATE users SET raw_passports = ?, raw_diplomas = ? WHERE id = ?",
                     (KEPT_PASSPORTS, KEPT_DIPLOMAS, kept["user_id"]))
        conn.execute("UPDATE purchases SET document_sante = ? WHERE id = ?", (KEPT_DOCUMENT, kept["purchase_id"]))
        conn.commit()
    finally:
        conn.close()


def _cell_date(member: SeedMember) -> str:
    return member["birth_date"].strftime("%d/%m/%Y") if member["birth_date"] else ""


def _row(member: SeedMember, **cells: str) -> Dict[str, str]:
    row = {"Nom": member["last_name"].upper(), "Prénom": member["first_name"], "N° de licence": member["licence"],
           "Date de naissance": _cell_date(member)}
    row.update({key.replace("_", " "): value for key, value in cells.items()})
    return row


def _name(member: SeedMember) -> str:
    return f"{member['last_name'].upper()} {member['first_name']}"


def write_ffme_file(season: str, folder: str) -> List[str]:
    """Writes the export into `folder`; returns the path then one line per case (what the preview should show)."""
    members = _members(season)
    licensed = _licensed(members)
    kept = _kept_member(members)
    used = {kept["user_id"]}
    rows: List[Dict[str, str]] = []
    cases: List[str] = []

    def take(predicate: Callable[[SeedMember], bool]) -> SeedMember:
        """A licensed member already « Terminé », not used by another case."""
        member = next(m for m in licensed if m["user_id"] not in used and normalize_status(m["status"]) == "Terminé"
                      and predicate(m))
        used.add(member["user_id"])
        return member

    # Changes by licence: passports and diplomas, the health document of the season, both
    passports = take(lambda m: True)
    rows.append(_row(passports, Passeports="Passeport Blanc, Passeport Jaune"))
    diploma = take(lambda m: (m["birth_date"] or datetime.date.max).year < 2005)
    rows.append(_row(diploma, Diplômes="Initiateur SAE, Juge de bloc"))
    health = take(lambda m: True)
    rows.append(_row(health, Passeports="Passeport Orange", **{"Document de santé": "Questionnaire de santé"}))
    cases += [f"Licence : {_name(passports)} → passeports",
              f"Licence : {_name(diploma)} → diplômes",
              f"Licence : {_name(health)} → passeports et document de santé"]

    # Empty cells keep the stored values
    rows.append(_row(kept))
    cases.append(f"Inchangé : {_name(kept)} garde {KEPT_PASSPORTS} / {KEPT_DIPLOMAS} / {KEPT_DOCUMENT} (cellules vides)")

    # Incomplete registrations (no licence, « Validé »): matched by name, licence given, status « Terminé »
    incomplete = [m for m in members if not m["licence"] and not is_cancelled(m["status"])
                  and (m["last_name"], m["first_name"]) != ("POTTER", "Harry")]
    for number, member in enumerate(incomplete, start=1):
        used.add(member["user_id"])
        rows.append(_row(member, **{"N° de licence": f"{700000 + number}"}))
    cases.append(f"Nom : {len(incomplete)} inscriptions incomplètes ({', '.join(_name(m) for m in incomplete)})"
                 " → licence 70000N, statut Validé → Terminé")

    # A sibling's licence: the birth date sends the row to the right child, the other one keeps the number
    families: Dict[str, List[SeedMember]] = {}
    for member in licensed:
        if member["user_id"] not in used:
            families.setdefault(member["last_name"], []).append(member)
    holder, sibling = next(family for family in families.values() if len(family) >= 2)[:2]
    used.update({holder["user_id"], sibling["user_id"]})
    rows.append(_row(sibling, **{"N° de licence": holder["licence"]}))
    cases.append(f"Nom : {_name(sibling)} a la licence {holder['licence']} de {_name(holder)}"
                 " → ⚠️ Licence déjà enregistrée sur …")

    # Homonyms: the birth date picks the adult Harry Potter; without it, nobody (manual link)
    adult_harry = next(m for m in members if (m["last_name"].upper(), m["first_name"]) == ("POTTER", "Harry")
                       and m["birth_date"] == HOMONYM_BIRTH)
    rows.append(_row(adult_harry, **{"N° de licence": "780731"}))
    rows.append({"Nom": "POTTER", "Prénom": "Harry"})
    cases += [f"Nom (homonymes, date de naissance) : POTTER Harry né le {HOMONYM_BIRTH:%d/%m/%Y} → licence 780731",
              "Non rapproché : POTTER Harry sans date de naissance (homonymes)"]

    # A birth date that disagrees with the only member of that name
    wrong_birth = take(lambda m: m["birth_date"] is not None)
    rows.append({**_row(wrong_birth), "Date de naissance": "01/01/1950"})
    cases.append(f"Non rapproché : {_name(wrong_birth)} né le 01/01/1950 (date de naissance différente, licence comprise)")

    # Two rows for the same member: Appliquer stays disabled until one is unticked
    duplicate = take(lambda m: True)
    rows.append(_row(duplicate, Passeports="Passeport Rouge"))
    rows.append({**_row(duplicate), "N° de licence": "", "Date de naissance": ""})
    cases.append(f"Doublon : {_name(duplicate)} rapproché par 2 lignes (licence et nom)")

    # Cancelled registration: user fields change, the status does not
    cancelled = next(m for m in members if m["licence"] == CANCELLED_LICENCE)
    rows.append(_row(cancelled, Passeports="Passeport Blanc"))
    cases.append(f"Licence : {_name(cancelled)} → passeports, ⚠️ Aucune inscription active sur la saison")

    # Unknown to the club
    rows.append({"Nom": "LOCKHART", "Prénom": "Gilderoy", "N° de licence": "599999", "Date de naissance": "26/01/1964"})
    cases.append("Non rapproché : LOCKHART Gilderoy (inconnu, à lier à la main ou à ignorer)")

    # Every other licensed member: matched by licence, nothing to change but the status of the incomplete ones
    others = [m for m in licensed if m["user_id"] not in used]
    rows += [_row(m) for m in others]
    to_finish = [m for m in others if normalize_status(m["status"]) != "Terminé"]
    unchanged = [m for m in others if m not in to_finish]
    if to_finish:
        cases.append(f"Licence : {', '.join(_name(m) for m in to_finish)} (licence de la saison passée)"
                     " → statut Validé → Terminé")
    cases.append(f"Inchangés : {len(unchanged) + 1} adhérents reconnus sans changement (dont {_name(kept)})")

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Liste des licenciés (données fictives du seed)"])
    sheet.append(HEADER)
    for row in rows:
        sheet.append([row.get(column, "") for column in HEADER])
    path = os.path.join(folder, FILE_NAME)
    workbook.save(path)
    return [path, *cases]
