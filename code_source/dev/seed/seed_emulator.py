"""
Fills the local Firestore emulator with FAKE data (Harry Potter universe).

    cd code_source
    set -a && source dev/dev.env && set +a
    python dev/seed/seed_emulator.py
    python dev/seed/seed_emulator.py --access-only   # keeps the data: only the login accounts and their roles

Fully resets the emulator database, then follows the production path:
1. temporary SQLite database with the current schema, filled by the same functions as
   the HelloAsso import (`MemberRepository.upsert_members`, `save_planning_data`, …),
   plus fake coordinates in the geocache (members map, never geocoded through Nominatim);
2. push to Firestore with `cloud_database.import_database` (real `crm_*` format);
3. PWA `adherents` / `planning` projection, coaches and competitions through
   `CompetitionRepository`.

Refuses to run outside dev mode (ALJ_ENV=dev + emulator + demo-alj project).
"""
import datetime
import json
import os
import random
import sys
import tempfile
import unicodedata

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

from infrastructure import runtime_env  # noqa: E402

SEED = 42
SEASON = "2026-2027"
PREVIOUS_SEASON = "2025-2026"
RETURNING_RATIO = 0.7          # share of members already registered the previous season
EMAIL_DOMAIN = "hogwarts.example"   # reserved domain: no e-mail can ever be delivered

# Fake Google accounts in the Auth emulator, one per role, listed in the access list (access_roles, see
# role_directory): (uid, e-mail, display name, role)
DEV_ACCOUNTS = [
    ("dev-dumbledore", "albus.dumbledore@alj-escalade.fr", "Albus Dumbledore", "admin"),
    ("dev-snape", f"severus.snape@{EMAIL_DOMAIN}", "Severus Snape", "coach"),
    ("dev-filch", f"argus.filch@{EMAIL_DOMAIN}", "Argus Filch", "readonly"),
]


def ensure_emulator() -> str:
    """Double guard: dev mode + emulator + demo-* project. Returns the Firestore host."""
    runtime_env.validate()
    host = runtime_env.firestore_emulator_host()
    project = runtime_env.project_id_override() or ""
    if not host or not project.startswith("demo-"):
        raise SystemExit("❌ Refused: this script only writes to the Firebase emulator "
                         "(ALJ_ENV=dev, FIRESTORE_EMULATOR_HOST, demo-* project). "
                         "Run: set -a && source dev/dev.env && set +a")
    return host


def reset_emulator(host: str, project: str) -> None:
    url = f"http://{host}/emulator/v1/projects/{project}/databases/(default)/documents"
    resp = requests.delete(url, timeout=30)
    resp.raise_for_status()


def drop_server_cache() -> None:
    """Deletes the dev server's SQLite cache (ALJ_DATA_DIR): the reset leaves no deletions
    to sync, and the server rebuilds its cache from the emulator."""
    from infrastructure.sqlite.connection import SqliteDatabase
    if not os.environ.get("ALJ_DATA_DIR"):
        # Without a dedicated folder, the default path would be this machine's database (data/): leave it alone.
        print("ℹ️  ALJ_DATA_DIR not set: dev server cache kept.")
        return
    db = SqliteDatabase.get_db_path()
    for path in (db, db + "-wal", db + "-shm"):
        if os.path.exists(path):
            os.remove(path)


def seed_auth_accounts(auth_host: str, project: str, reset: bool = True) -> None:
    """Recreates the login accounts (simulated google.com provider); their roles are in the access list. Without
    `reset`, the other accounts are kept and a dev account that exists already is signed in again (same account)."""
    base = f"http://{auth_host}"
    if reset:
        requests.delete(f"{base}/emulator/v1/projects/{project}/accounts", timeout=30).raise_for_status()
    for sub, email, name, _role in DEV_ACCOUNTS:
        id_token = json.dumps({"sub": sub, "email": email, "email_verified": True, "name": name})
        requests.post(
            f"{base}/identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=demo",
            json={"postBody": f"id_token={id_token}&providerId=google.com",
                  "requestUri": "http://localhost", "returnSecureToken": True},
            timeout=30).raise_for_status()


def seed_access_roles() -> None:
    """The access list (Administration › Accès): one entry per dev account (rewritten as seeded), one history entry
    each. The only source of roles: without it, no dev account can sign in."""
    from infrastructure.firestore.access_store import FirestoreAccessStore
    from services.access.rules import INVITATION_DAYS, iso

    store = FirestoreAccessStore()
    now = datetime.datetime.now(datetime.timezone.utc)
    at = iso(now)
    for _sub, email, name, role in DEV_ACCOUNTS:
        store.save_role({"email": email, "role": role, "display_name": name, "last_sign_in_at": None,
                         "created_at": at, "created_by": "seed", "updated_at": at, "updated_by": "seed",
                         "invited_at": None, "invitation_expires_at": None, "invitation_sent_at": None, "accepted_at": None})
        store.add_history({"at": at, "author": "seed", "action": "added", "target_email": email,
                           "old_role": None, "new_role": role})
    # Two invitations nobody accepted, to see their statuses on the page (no emulator account: nobody can sign in)
    for email, name, invited_days_ago in ((f"luna.lovegood@{EMAIL_DOMAIN}", "Luna Lovegood", 2),
                                          (f"gilderoy.lockhart@{EMAIL_DOMAIN}", "Gilderoy Lockhart", 10)):
        invited = now - datetime.timedelta(days=invited_days_ago)
        store.save_role({"email": email, "role": "coach", "display_name": name, "last_sign_in_at": None,
                         "created_at": iso(invited), "created_by": "seed", "updated_at": iso(invited), "updated_by": "seed",
                         "invited_at": iso(invited), "invitation_expires_at": iso(invited + datetime.timedelta(days=INVITATION_DAYS)),
                         "invitation_sent_at": iso(invited), "accepted_at": None})


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def planning_items(coaches):
    """Season slots (birth-date bounds consistent with age_rules)."""
    snape, mcgonagall, flitwick, sprout, lupin, hagrid = coaches
    # `type` and `jour` values are parsed by the app (planning Excel export, presence sheets):
    # they keep the application's French vocabulary. Everything else is English, except
    # « Autonome » in autonomous slot names/tariffs: `is_autonome_creneau` looks for that word.
    items = [
        ("Leisure - Children 2017-2019", "cours", "U8-U10", "Mercredi", "14:00-15:30",
         [hagrid, sprout], ["Leisure - Children born 2017, 2018, 2019"], "2017-01-01", "2019-12-31"),
        ("Leisure - Lower school (Group A)", "cours", "U12-U15", "Lundi", "18:30-20:00",
         [flitwick], ["Leisure lower school - born 2012, 2013, 2014, 2015 - Monday 18:30"],
         "2012-01-01", "2015-12-31"),
        ("Leisure - Upper school", "cours", "U16-U18", "Jeudi", "18:30-20:00",
         [lupin], ["Leisure upper school - born 2009, 2010, 2011"], "2009-01-01", "2011-12-31"),
        ("Competition - U11-U13", "compétition", "U11-U13", "Mercredi", "16:00-18:00",
         [snape, mcgonagall], ["Competition U11-U13"], "2014-01-01", "2017-12-31"),
        ("Competition - U15-U17-U19", "compétition", "U15-U19", "Vendredi", "18:00-20:00",
         [snape], ["Competition U15 U17 - born 2008, 2009, 2010, 2011, 2012, 2013"],
         "2008-01-01", "2013-12-31"),
        ("Leisure - Adult beginners", "cours", "Adults", "Mardi", "20:00-22:00",
         [mcgonagall], ["Adult beginners course"], "", ""),
        ("Autonome", "autonome", "Adults", "Lundi / Jeudi", "20:00-22:30",
         [], ["Autonome adults"], "", ""),
        ("Autonome Bloc", "autonome", "Adults", "Samedi", "10:00-12:00",
         [], ["Autonome bouldering"], "", ""),
    ]
    return [
        {"id": i, "groupe": group, "type": kind, "categorie_age": age_cat, "jour": day, "horaires": hours,
         "encadrants": coach_names, "helloasso_tarifs": rates, "naissance_min": born_min, "naissance_max": born_max,
         "whatsapp_link": ""}
        for i, (group, kind, age_cat, day, hours, coach_names, rates, born_min, born_max)
        in enumerate(items, start=1)
    ]


AMOUNT_BY_TYPE = {"cours": 210.0, "compétition": 260.0, "autonome": 150.0}


def ascii_slug(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum() or c == "-")


def build_people(fake, rng, planning):
    """One person = stable identity + slot picked from their birth year."""
    from hp_names import ADULTS, STUDENTS
    youth = [p for p in planning if p["naissance_min"]]
    adults = [p for p in planning if not p["naissance_min"]]
    people = []
    for first, last, sex in STUDENTS:
        group = rng.choice(youth)
        y_min, y_max = int(group["naissance_min"][:4]), int(group["naissance_max"][:4])
        birth = fake.date_between_dates(datetime.date(y_min, 1, 1), datetime.date(y_max, 12, 31))
        people.append({"first": first, "last": last, "sex": sex, "birth": birth, "group": group,
                       "minor": True})
    for first, last, sex in ADULTS:
        birth = fake.date_between_dates(datetime.date(1960, 1, 1), datetime.date(2004, 12, 31))
        people.append({"first": first, "last": last, "sex": sex, "birth": birth,
                       "group": rng.choice(adults), "minor": False})
    return people


def member_record(fake, rng, person, season, order_no):
    """Record in the HelloAsso import format (keys read by schema_v2).

    Keys, the "Validé" / "Terminé" statuses and "Oui"/"Non" answers are the HelloAsso form's own
    (French) values, matched by the app; every other value is English. Members with a licence number are
    "Terminé" (licence confirmed: only they can be added to a competition), the incomplete ones "Validé"."""
    from hp_names import PARENTS
    from infrastructure.sqlite.schema_v2 import DOB_COLUMN
    first, last, group = person["first"], person["last"], person["group"]
    email = f"{ascii_slug(first)}.{ascii_slug(last)}@{EMAIL_DOMAIN}"
    if person["minor"]:
        payer_first = PARENTS.get(last) or fake.first_name()
        payer_email = f"{ascii_slug(payer_first)}.{ascii_slug(last)}@{EMAIL_DOMAIN}"
    else:
        payer_first, payer_email = first, email
    start_year = int(season[:4])
    order_date = fake.date_between_dates(datetime.date(start_year, 6, 20), datetime.date(start_year, 9, 30))
    incomplete = rng.random() < 0.12      # a few incomplete records (real-world cases to test)
    insured = rng.random() < 0.8
    autonomous = group["type"] == "autonome"
    # Club autonomy validations (normally imported from Autonomes_*.xlsx) and, for some minors,
    # the parental authorisations that add them to the autonomous attendance sheet.
    red_badge = rng.random() < (0.7 if autonomous else 0.15)
    bouldering = rng.random() < (0.8 if autonomous else 0.2)
    auth_autonomous = person["minor"] and rng.random() < 0.15
    auth_family = person["minor"] and rng.random() < 0.1
    return {
        "order_ref": f"DEV-{season[:4]}-{order_no:04d}",
        "order_date": order_date.strftime("%d/%m/%Y"),
        "status": "Validé" if incomplete else "Terminé",
        "payer_lastName": last.upper(),
        "payer_firstName": payer_first,
        "payer_email": payer_email,
        "tarif_name": group["helloasso_tarifs"][0],
        "amount": AMOUNT_BY_TYPE.get(group["type"], 200.0),
        "user_lastName": last.upper(),
        "user_firstName": first,
        DOB_COLUMN: person["birth"].strftime("%d/%m/%Y"),
        "champ_Sexe": "Female" if person["sex"] == "F" else "Male",
        "champ_Nationalité": "British",
        "champ_Adresse : numéro et nom de rue": fake.street_address(),
        "champ_Code postal": fake.postcode(),
        "champ_Ville": rng.choice(["Hogsmeade", "Godric's Hollow", "Little Whinging", "Ottery St Catchpole"]),
        "champ_Pays": "United Kingdom",
        "champ_Téléphone ": "" if incomplete else fake.phone_number(),
        "champ_Adresse mail pour la réception des informations du club": email,
        "champ_Personne à prévenir en cas d'urgence - NOM  et PRENOM en majuscule":
            f"{last.upper()} {payer_first.upper()}" if person["minor"] else fake.name().upper(),
        "champ_Personne à prévenir en cas d'urgence - Téléphone": fake.phone_number(),
        "champ_Numéro de Licence FFME (6 chiffres)": "" if incomplete else str(rng.randint(100000, 999999)),
        "champ_En cas de prise de vue (Photo ou vidéo), j'autorise": "Oui" if rng.random() < 0.9 else "Non",
        "champ_Je m'engage à compléter mon questionnaire de santé": "" if incomplete else "Oui",
        "opt_Assurance Base": "Oui" if insured else "Non",
        "opt_Montant Assurance Base": 10.0 if insured else 0.0,
        "badge_rouge": "Oui" if red_badge else "Non",
        "autonomie_bloc": "Oui" if bouldering else "Non",
        "parental_auth_autonomous": "Oui" if auth_autonomous else "Non",
        "parental_auth_family": "Oui" if auth_family else "Non",
    }


# Members map: the fake towns placed on real towns around the club, each address a few hundred metres apart
TOWN_COORDINATES = {
    "HOGSMEADE": (45.795, 5.045),              # Jonage
    "GODRIC'S HOLLOW": (45.768, 5.003),        # Meyzieu
    "LITTLE WHINGING": (45.755, 5.068),        # Pusignan
    "OTTERY ST CATCHPOLE": (45.803, 5.083),    # Jons
}


def fill_geocache(rng):
    """Fake coordinates for every address the map geocodes (the server's own map code lists them), so that the
    dev map has markers without calling Nominatim on made-up addresses."""
    from api.reports.map import map_points
    from infrastructure.sqlite.geocache import GeocacheRepository

    class Collect:
        def __init__(self):
            self.addresses = []

        def add_task(self, func, addresses):
            self.addresses.extend(addresses)

    collect = Collect()
    map_points("Toutes les saisons", collect)
    for address in sorted(set(collect.addresses)):
        town = next((t for t in TOWN_COORDINATES if f", {t}, France" in address), "HOGSMEADE")
        lat, lon = TOWN_COORDINATES[town]
        GeocacheRepository.save_geocode(address, lat + rng.uniform(-0.008, 0.008), lon + rng.uniform(-0.012, 0.012))
    return len(collect.addresses)


EMAIL_TEMPLATES = [
    ("Welcome", "Welcome to the club, {first_name}!",
     "Hello {first_name},\n\nYour climbing membership is confirmed. "
     "See you at your first session!\n\nThe committee"),
    ("Competition call-up", "Call-up: {name_competition}",
     "Hello {first_name},\n\nYou have been selected for {name_competition} on {date_competition}. "
     "Entry fee: €{montant_competition}.\n\nThe coaches"),
]


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
def build_sqlite(path, fake, rng, coach_names):
    from infrastructure.sqlite.connection import SqliteDatabase
    from infrastructure.sqlite.email_templates import EmailTemplateRepository
    from infrastructure.sqlite.members import MemberRepository
    from infrastructure.sqlite.planning import PlanningRepository
    SqliteDatabase.set_db_path(path)
    SqliteDatabase.setup_database(force=True)

    planning = planning_items(coach_names)
    PlanningRepository.save_planning_data(planning)

    people = build_people(fake, rng, planning)
    current = [member_record(fake, rng, p, SEASON, i) for i, p in enumerate(people, start=1)]
    returning = [p for p in people if rng.random() < RETURNING_RATIO]
    previous = [member_record(fake, rng, p, PREVIOUS_SEASON, i) for i, p in enumerate(returning, start=1)]
    MemberRepository.upsert_members(previous, PREVIOUS_SEASON)
    MemberRepository.upsert_members(current, SEASON)
    # Own random stream: the rest of the seed data stays the same
    fill_geocache(random.Random(SEED))  # noqa: S311 - reproducible fake coordinates, not security

    for name, subject, body in EMAIL_TEMPLATES:
        EmailTemplateRepository.save_email_template(name, subject, body, "", "ALJ Escalade (dev)")
    return len(current), len(previous)


def seed_competitions(coach_ids):
    from domain.competitions.models import STATUT_CLOSE, STATUT_EN_COURS, STATUT_EN_PREPARATION, Competition
    from infrastructure.firestore.competitions import participants
    from infrastructure.firestore.competitions import competitions, member_directory

    snape, mcgonagall, flitwick = coach_ids[0], coach_ids[1], coach_ids[2]
    today = datetime.date.today()
    # id_ffme: the competition number members type on the HelloAsso form (automatic links)
    specs = [
        ("Diagon Alley Bouldering Cup", "1203", today - datetime.timedelta(days=35), 12.0, STATUT_CLOSE, snape, None),
        ("Hogwarts Lead Open", "1457", today + datetime.timedelta(days=12), 15.0, STATUT_EN_COURS, snape, mcgonagall),
        ("Regional Championship U15-U19", "1622", today + datetime.timedelta(days=40), 20.0, STATUT_EN_PREPARATION, snape, flitwick),
        ("Hogsmeade Friendly Contest", "", today + datetime.timedelta(days=75), 8.0, STATUT_EN_PREPARATION, mcgonagall, None),
        # Ended within the results batch window (30 days), unlike the 35-day-old cup: dev/seed/mycompet_state.py
        # publishes its results on the fake MyCompet
        ("Gringotts Bouldering Open", "1688", today - datetime.timedelta(days=5), 12.0, STATUT_CLOSE, flitwick, None),
    ]
    competitors = [a["id"] for a in member_directory.list_members(competition_only=True, statuses=["Terminé"])]
    rng = random.Random(SEED)
    base_id = int(datetime.datetime(today.year, today.month, today.day).timestamp() * 1000)
    seeded = []
    for i, (name, number, date, price, status, coach1, coach2) in enumerate(specs):
        comp = Competition(id=base_id + i, id_ffme=number, nom=name, date_competition=date.isoformat(), prix=price,
                           statut=status, coach_ids=[c for c in (coach1, coach2) if c is not None])
        comp.id = competitions.save_competition(comp)
        seeded.append(comp)
        for member_id in rng.sample(competitors, k=min(len(competitors), rng.randint(4, 9))):
            participants.add_participant(comp.id, member_id, selectionne=rng.random() < 0.8)
    return seeded, len(competitors)


HELLOASSO_FORM = "competitions-2026-2027-dev"


def helloasso_item(item_id, order_id, user, payer, amount, date, state="Processed", fields=(), payments=None,
                   options=()):
    """HelloAsso v5 item as `get_items(..., withDetails=true)` returns it (amounts in cents).

    `fields`: (name, answer) pairs; a pair (name, answer, "value") stores the answer under `value`,
    as some HelloAsso forms do."""
    first, last = user
    payer_first, payer_last = payer
    when = f"{date.isoformat()}T{10 + item_id % 9:02d}:{item_id * 7 % 60:02d}:00+02:00"
    cents = int(round(amount * 100))
    return {
        "id": item_id,
        "name": "Competition entry",
        "type": "Registration",
        "state": state,
        "amount": cents,
        "initialAmount": cents,
        "priceCategory": "Fixed",
        "user": {"firstName": first, "lastName": last},
        "payer": {"firstName": payer_first, "lastName": payer_last,
                  "email": f"{ascii_slug(payer_first)}.{ascii_slug(payer_last)}@{EMAIL_DOMAIN}",
                  "city": "Hogsmeade", "zipCode": "HG1 7AA", "country": "GBR"},
        "order": {"id": order_id, "date": when, "formSlug": HELLOASSO_FORM, "formType": "Event",
                  "formName": "Competitions 2026-2027 (dev)", "organizationName": "ALJ Escalade (dev)"},
        "payments": payments if payments is not None else [
            {"id": order_id * 10, "amount": cents, "state": "Authorized", "date": when, "paymentMeans": "Card"}],
        "customFields": [{"name": f[0], "type": "TextInput", f[2] if len(f) > 2 else "answer": f[1]}
                         for f in fields],
        "options": [{"name": name, "amount": int(round(price * 100)), "customFields": []} for name, price in options],
    }


def seed_helloasso_items(competitions):
    """HelloAsso payments of the competition campaign (« HelloAsso » pane), one case each: linked
    automatically (licence or name + competition number), linked by a coach, waiting for a coach
    (unknown competition, unknown payer, no field filled, cheque not cashed yet) and ignored
    (test payment, refunded duplicate). Goes through the same steps as POST /api/helloasso/sync."""
    from domain.competitions import matching
    from hp_names import PARENTS
    from infrastructure.firestore.competition_repository import CompetitionRepository
    from infrastructure.firestore.competitions import member_directory

    cup, lead_open, regional = competitions[0], competitions[1], competitions[2]
    members = [a for a in member_directory.list_members(competition_only=True) if a.get("num_licence")]
    if len(members) < 8:
        print(f"⚠️  HelloAsso items skipped: {len(members)} competitors with a licence (8 needed)")
        return 0
    today = datetime.date.today()

    def name(member):
        return member["prenom"], member["nom"].title()

    def licence(member):
        return ("Numéro de licence FFME", member["num_licence"])

    def number(comp):
        return ("Numéro de la compétition", comp.id_ffme)

    def days_ago(days):
        return today - datetime.timedelta(days=days)

    item_id, order_id = 41001, 82001
    items = []

    def add(member_or_name, comp_price, date, payer=None, **kwargs):
        nonlocal item_id, order_id
        user = name(member_or_name) if isinstance(member_or_name, dict) else member_or_name
        items.append(helloasso_item(item_id, order_id, user, payer or user, comp_price, date, **kwargs))
        item_id, order_id = item_id + 1, order_id + 1
        return items[-1]["id"]

    # Linked automatically: licence + competition number (a parent pays for some)
    add(members[0], cup.prix, days_ago(60), fields=[licence(members[0]), number(cup)])
    parent = (PARENTS.get(name(members[1])[1]) or "Dorothy", name(members[1])[1])
    add(members[1], cup.prix, days_ago(58), payer=parent, fields=[licence(members[1]), number(cup)])
    add(members[2], lead_open.prix, days_ago(9), fields=[licence(members[2]), number(lead_open)])
    add(members[3], lead_open.prix, days_ago(8), fields=[licence(members[3]), number(lead_open)],
        options=[("Bus to the venue", 5.0)])
    # Linked automatically by name (no licence typed), answer under `value`, paid in two instalments
    half = regional.prix / 2
    add(members[4], regional.prix, days_ago(5), fields=[("Numéro de la compétition", regional.id_ffme, "value")],
        payments=[{"id": 1, "amount": int(half * 100), "state": "Authorized", "date": f"{days_ago(5)}T18:00:00+02:00",
                   "paymentMeans": "Card"},
                  {"id": 2, "amount": int(half * 100), "state": "Pending", "date": f"{today + datetime.timedelta(days=25)}"
                   "T18:00:00+02:00", "paymentMeans": "Card"}])
    # Linked by a coach: the competition number was mistyped
    manual = add(members[5], lead_open.prix, days_ago(7),
                 fields=[licence(members[5]), ("Numéro de la compétition", "Hogwart lead"),
                         ("Compétition concernée", "Lead open at Hogwarts")])
    # Waiting for a coach
    add(members[6], 18.0, days_ago(4), fields=[licence(members[6]), ("Compétition concernée", "Gringotts Boulder Jam")])
    add(("Mundungus", "Fletcher"), lead_open.prix, days_ago(3), fields=[number(lead_open)])
    add(("Gilderoy", "Lockhart"), 7.5, days_ago(2))
    add(members[7], regional.prix, days_ago(1), state="Waiting", fields=[licence(members[7]), number(regional)],
        payments=[{"id": 3, "amount": int(regional.prix * 100), "state": "Waiting", "date": f"{days_ago(1)}T09:30:00+02:00",
                   "paymentMeans": "Check"}])
    # Ignored by a coach
    test_payment = add(("Albus", "Dumbledore"), 1.0, days_ago(70), fields=[("Compétition concernée", "Test")])
    duplicate = add(members[0], cup.prix, days_ago(59), state="Refunded", fields=[licence(members[0]), number(cup)],
                    payments=[{"id": 4, "amount": int(cup.prix * 100), "state": "Refunded",
                               "date": f"{days_ago(59)}T11:00:00+02:00", "paymentMeans": "Card"}])

    summarized = matching.summarize_items(items)
    CompetitionRepository.update_helloasso_mirror(summarized, items, HELLOASSO_FORM)
    comps = [{"id": c.id, "id_ffme": c.id_ffme, "nom": c.nom} for c in competitions]
    CompetitionRepository.replace_auto_links(matching.auto_link_items(summarized, comps, member_directory.list_members(), {}))
    CompetitionRepository.save_manual_link(manual, lead_open.id, members[5]["id"], "Mistyped competition number on the form")
    CompetitionRepository.set_item_ignored(test_payment, True, "Test payment", by=DEV_ACCOUNTS[0][1])
    CompetitionRepository.set_item_ignored(duplicate, True, "Duplicate payment, refunded", by=DEV_ACCOUNTS[1][1])
    CompetitionRepository.apply_links_to_participants()
    return len(items)


def seed_access_only(project: str) -> int:
    """Emulator data seeded before the access list existed (or roles changed on the page): the dev accounts and their
    roles, everything else kept."""
    seed_auth_accounts(os.environ["FIREBASE_AUTH_EMULATOR_HOST"], project, reset=False)
    seed_access_roles()
    print("🔑 Login accounts: " + ", ".join(f"{email} ({role})" for _, email, _, role in DEV_ACCOUNTS))
    print("✅ Done (data kept)")
    return 0


def main() -> int:
    host = ensure_emulator()
    project = runtime_env.project_id_override()
    if "--access-only" in sys.argv[1:]:
        return seed_access_only(project)

    from faker import Faker
    from hp_names import COACHES
    from infrastructure.firestore.cloud_sync.bootstrap import import_database
    from infrastructure.firestore.cloud_sync.rest_store import RestStore
    from infrastructure.firestore.competitions import coaches, member_directory

    Faker.seed(SEED)
    fake = Faker("en_GB")
    rng = random.Random(SEED)

    print(f"🧹 Resetting the emulator ({host}, project {project})")
    reset_emulator(host, project)
    drop_server_cache()

    workdir = tempfile.mkdtemp(prefix="alj_seed_")
    db_path = os.path.join(workdir, "seed.db")
    n_cur, n_prev = build_sqlite(db_path, fake, rng, COACHES)
    print(f"🧙 {n_cur} memberships {SEASON}, {n_prev} memberships {PREVIOUS_SEASON} (re-registrations)")

    written = import_database(db_path, RestStore())
    print(f"☁️  crm_* collections: {written}")

    # Coaches: fixed ids, Snape first (id 1)
    coach_ids = []
    for i, name in enumerate(COACHES, start=1):
        coach_ids.append(coaches.save_coach(name, coach_id=i))
    print(f"🧑‍🏫 Coaches: {', '.join(COACHES)}")

    # Projection read by the PWA (adherents / planning), from the seed SQLite database
    report = member_directory.rebuild_member_directory(SEASON)
    if report.get("errors"):
        print(f"⚠️  adherents projection: {report['errors']}")

    competitions, n_competitors = seed_competitions(coach_ids)
    print(f"🏆 {len(competitions)} competitions ({n_competitors} eligible competitors)")
    print(f"🧾 {seed_helloasso_items(competitions)} HelloAsso payments")

    seed_auth_accounts(os.environ["FIREBASE_AUTH_EMULATOR_HOST"], project)
    seed_access_roles()
    print("🔑 Login accounts: " + ", ".join(f"{email} ({role})" for _, email, _, role in DEV_ACCOUNTS))
    print("✅ Done — emulator UI: http://localhost:4000/firestore")
    return 0


if __name__ == "__main__":
    runtime_env.load_env_files()  # .env files as the server reads them (never at import: tests call main())
    sys.exit(main())
