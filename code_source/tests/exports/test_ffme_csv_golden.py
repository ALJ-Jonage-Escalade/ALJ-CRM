"""FFME CSV export (exports/membership_excel.py), byte for byte on fake members: the golden master that runs in CI.

The expected rows were produced by the export before its refactoring (desloppify batch 6) and follow the club's
reference format; tests/exports/test_ffme_golden_master.py still compares real data, on a workstation only.
A change here changes the file sent to the FFME: renew the expected rows only with the club's approval.
"""

from __future__ import annotations

from exports.membership_excel import FFME_CSV_HEADERS, _ffme_csv_rows, ffme_csv_bytes

MEMBERS = [
    # Renewal: licence stored as a float, everything filled in, B++ and all options
    {"last_name": "Potter", "first_name": "Harry", "licence_ffme": "636947.0", "birth_date": "31/07/2010", "sex": "M",
     "nationality": "Française", "country": "France", "address": "4 Privet Drive", "zip_code": "1234", "city": "Jonage",
     "phone": "+33 6 12 34 56 78", "email_primary": "Harry.Potter@Hogwarts.example", "email_secondary": "hp@owl.example",
     "emergency1_name": "Lily Potter", "emergency1_phone": "06 98 76 54 32", "is_tribe": "Non",
     "opt_Assurance Base": "Oui", "opt_Assurance Base +": "Oui", "opt_Assurance Base ++": "Oui",
     "opt_Assurance Option ski de piste": "Oui", "opt_Assurance Option VTT": "true", "opt_Assurance Option Trail": "VRAI",
     "tarif_name": "Jeunes", "amount": 195.0, "status": "Validé", "order_ref": "CMD-1"},
    # First licence, adult, date object, missing contact fields filled with the club defaults, B+
    {"last_name": "granger", "first_name": "Hermione", "licence_ffme": "", "birth_date": "1979-09-19", "sex": "F",
     "nationality": None, "country": None, "address": "", "zip_code": None, "city": "", "phone": "0612345678",
     "email_primary": "", "payer_email": "Parent.Granger@Example.org", "emergency1_name": "Dumbledore", "emergency1_phone": "",
     "opt_Assurance Base +": "OUI", "tarif_name": "Adulte", "amount": 150, "status": "Validé", "order_ref": "CMD-2"},
    # Family licence (tribe), foreign country and Swedish nationality, base insurance
    {"last_name": "Weasley", "first_name": "Ron", "licence_ffme": "1234567", "birth_date": "1980-03-01", "sex": "M",
     "nationality": "Suédoise", "country": "Belgique", "address": "Le Terrier", "zip_code": "B-1000", "city": "Bruxelles",
     "phone": "", "email_primary": "ron@burrow.example", "is_tribe": "Oui", "opt_Assurance Base": "Oui",
     "tarif_name": "Famille", "amount": 120.0, "status": "Validé", "order_ref": "CMD-3"},
    # Two-letter nationality, no email and no licence: the club's contact address
    {"last_name": "Lovegood", "first_name": "Luna", "licence_ffme": "12", "birth_date": "13/02/2011", "sex": "F",
     "nationality": "IE", "country": "Irlande", "address": "", "zip_code": "", "city": "", "phone": "33612345678",
     "tarif_name": "Jeunes", "amount": 0.0, "commentaires_correctif": "Ajout manuel par le bureau", "status": "", "order_ref": "CMD-4"},
    # Done ('Terminé'): only with include_termine
    {"last_name": "Londubat", "first_name": "Neville", "licence_ffme": "765432", "birth_date": "30/07/1980", "sex": "M",
     "tarif_name": "Adulte", "amount": 150.0, "status": "Terminé", "order_ref": "CMD-5"},
    # Left out with a reason
    {"last_name": "Malefoy", "first_name": "Drago", "birth_date": "", "sex": "M", "tarif_name": "Adulte", "amount": 150.0,
     "status": "Validé", "order_ref": "CMD-6"},
    {"last_name": "Diggory", "first_name": "Cedric", "licence_ffme": "", "birth_date": "01/09/1977", "sex": "",
     "tarif_name": "Adulte", "amount": 150.0, "status": "Validé", "order_ref": "CMD-7"},
    # Left out silently: waiting list, nothing paid, cancelled
    {"last_name": "Lestrange", "first_name": "Bellatrix", "birth_date": "01/01/1970", "sex": "F", "tarif_name": "Liste d'attente",
     "amount": 150.0, "status": "Validé", "order_ref": "CMD-8"},
    {"last_name": "Rogue", "first_name": "Severus", "birth_date": "09/01/1960", "sex": "M", "tarif_name": "Adulte", "amount": 0.0,
     "status": "Validé", "order_ref": "CMD-9"},
    {"last_name": "Jedusor", "first_name": "Tom", "birth_date": "31/12/1926", "sex": "M", "tarif_name": "Adulte", "amount": 150.0,
     "status": "Annulé", "order_ref": "CMD-10"},
    # Unknown names, no sex but a renewal
    {"last_name": "", "first_name": None, "licence_ffme": 98765, "birth_date": "02/05/2009", "sex": None,
     "tarif_name": "Adulte", "amount": 150.0, "status": "Validé", "order_ref": "CMD-11"},
]

EXPECTED_ROWS = [
    ';GRANGER;Hermione;19/09/1979;F;FR;ADRESSE NON COMMUNIQUEE;;69330;JONAGE;FR;;0612345678;parent.granger@example.org;;DUMBLEDORE;;;;;;;A;B+;NON;NON;NON;NON;NON;NON',
    '98765;INCONNU;INCONNU;02/05/2009;;FR;;;;;FR;;;;;;;;;;;;A;RC;NON;NON;NON;NON;NON;NON',
    ';LOVEGOOD;Luna;13/02/2011;F;IE;ADRESSE NON COMMUNIQUEE;;;JONAGE;IR;;33612345678;contact@alj-escalade.fr;;;;;;;;;J;RC;NON;NON;NON;NON;NON;NON',
    '636947;POTTER;Harry;31/07/2010;H;FR;4 Privet Drive;;01234;JONAGE;FR;;0612345678;harry.potter@hogwarts.example;hp@owl.example;POTTER;Lily;0698765432;;;;;J;B++;OUI;NON;OUI;OUI;NON;NON',
    '1234567;WEASLEY;Ron;01/03/1980;H;;Le Terrier;;1000;BRUXELLES;BE;;;ron@burrow.example;;;;;;;;;F;B;NON;NON;NON;NON;NON;NON',
]
# include_termine adds the member already declared ('Terminé'), in its place by name
DONE_ROW = '765432;LONDUBAT;Neville;30/07/1980;H;FR;;;;;FR;;;;;;;;;;;;A;RC;NON;NON;NON;NON;NON;NON'
EXPECTED_IGNORED = [
    "⚠️ [IGNORÉ] MALEFOY Drago (Commande CMD-6) : date de naissance absente ou invalide ('')",
    '⚠️ [IGNORÉ] DIGGORY Cedric (Commande CMD-7) : sexe non renseigné',
]


def _csv(rows: list[str]) -> bytes:
    return "\r\n".join([";".join(FFME_CSV_HEADERS), *rows, ""]).encode("utf-8")


def test_ffme_csv_bytes_matches_the_golden_rows() -> None:
    assert ffme_csv_bytes(MEMBERS) == _csv(EXPECTED_ROWS)


def test_ffme_csv_bytes_with_done_members() -> None:
    expected = EXPECTED_ROWS[:2] + [DONE_ROW] + EXPECTED_ROWS[2:]
    assert ffme_csv_bytes(MEMBERS, include_termine=True) == _csv(expected)


def test_ffme_csv_bytes_does_not_depend_on_the_order_of_the_members_read() -> None:
    assert ffme_csv_bytes(list(reversed(MEMBERS))) == _csv(EXPECTED_ROWS)


def test_ffme_csv_rows_lists_the_members_left_out() -> None:
    assert _ffme_csv_rows(MEMBERS, include_termine=False)[1] == EXPECTED_IGNORED


def test_ffme_csv_rows_accepts_a_date_object_as_birth_date() -> None:
    import datetime

    member = {**MEMBERS[1], "birth_date": datetime.date(1979, 9, 19)}
    assert _ffme_csv_rows([member], include_termine=False)[0][0][3] == "19/09/1979"
