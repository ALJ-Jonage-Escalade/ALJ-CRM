"""
Rapprochement HelloAsso <-> participants d'une compétition (logique pure, testable).

Entrées : items bruts de l'API HelloAsso v5 (infrastructure.helloasso.api.fetch_form_items) et les
participants d'une compétition (participants.list_participants).
Sorties : mises à jour de statut de paiement + rapport d'anomalies.

Croisement par ordre de priorité :
1. Numéro de licence FFME (champ personnalisé du formulaire HelloAsso) ;
2. Nom + prénom normalisés (accents/tirets/majuscules neutralisés).

Contrôle additionnel : le champ personnalisé « Compétition concernée » du formulaire
HelloAsso doit contenir le n° d'épreuve attendu (id_ffme communiqué dans l'invitation).
Un paiement sans ce n° (champ vide ou non conforme) n'est PAS marqué « Payé »
automatiquement : il est retourné dans `manual_review` pour correction manuelle.
"""
import re
from typing import NamedTuple, Optional

from domain.competitions.models import PAIEMENT_PAYE
from domain.utils import is_helloasso_url, normalize_name, normalize_string

# États HelloAsso consideres comme un paiement valide
STATUTS_PAYES = {"processed", "validated", "registered"}

# Motifs reconnus pour extraire le type de formulaire depuis une URL HelloAsso
_URL_TYPE_MAP = {
    "evenements": "Event",
    "formulaires": None,      # type explicite dans le segment suivant
    "adhesions": "Membership",
    "campagnes": "Campaign",
    "dons": "Donation",
    "boutiques": "Shop",
    "crowdfundings": "Crowdfunding",
}


def parse_campaign_identifier(ref: str) -> dict:
    """Analyse l'identifiant / l'URL de campagne saisi par l'utilisateur.

    Accepte :
    - une URL complète (https://www.helloasso.com/associations/{org}/evenements/{slug}
      ou .../formulaires/{FormType}/{slug}) ;
    - un couple explicite « FormType:slug » (ex : « Event:competition-u11 ») ;
    - un slug brut (type « Event » par défaut : les compétitions sont des événements).

    Retourne {"form_type": str, "slug": str} ou lève ValueError si non exploitable.
    """
    raw = str(ref or "").strip()
    if not raw:
        raise ValueError("Aucun identifiant de campagne HelloAsso fourni.")

    if is_helloasso_url(raw):
        path = re.split(r"associations/[^/]+/+", raw, maxsplit=1, flags=re.IGNORECASE)
        segments = [s.strip("/ ") for s in path[-1].split("/")]
        segments = [s for s in segments if s]
        if len(segments) >= 2:
            head = segments[0].lower()
            if head == "formulaires" and len(segments) >= 3:
                return {"form_type": segments[1].strip(), "slug": segments[2].strip()}
            if head in _URL_TYPE_MAP and _URL_TYPE_MAP[head]:
                return {"form_type": _URL_TYPE_MAP[head], "slug": segments[1].strip()}
        raise ValueError(f"URL HelloAsso non reconnue : {raw}")

    if ":" in raw:
        ftype, _, slug = raw.partition(":")
        ftype, slug = ftype.strip(), slug.strip()
        if ftype and slug:
            return {"form_type": ftype, "slug": slug}

    return {"form_type": "Event", "slug": raw}


def extract_licence(item: dict) -> str:
    """Extrait le numéro de licence FFME des champs personnalisés de l'item.

    Comme partout dans le projet, la réponse peut résider dans `answer` ou `value`.
    """
    for field in item.get("customFields") or []:
        name = str(field.get("name") or "")
        if "licence" in name.lower():
            val = field.get("answer") or field.get("value") or ""
            digits = re.sub(r"\D", "", str(val or ""))
            if digits:
                return digits
    return ""


def extract_competition_number(item: dict, fallback: bool = True) -> str:
    """Extrait la valeur du champ personnalisé « Numéro de la compétition » de l'item.

    Ce champ est saisi par l'adhérent sur le formulaire HelloAsso (n° d'épreuve
    communiqué dans l'e-mail d'invitation via la variable {no_competition}).
    Comme partout dans le projet, la réponse peut résider dans `answer` ou `value`.

    - fallback=True (défaut) : si le champ n° est absent/vide, repli sur la valeur
      de « Compétition concernée » (utile pour le rattachement) ;
    - fallback=False : retourne uniquement la valeur du champ n° (affichage fidèle
      à HelloAsso : rien n'est affiché si l'adhérent n'a rien saisi).
    """
    # 1. On cherche d'abord le champ d'identifiant / numéro précis (ex: "Numéro de la compétition")
    for field in item.get("customFields") or []:
        name = normalize_string(field.get("name") or "")
        if "numero" in name and "competition" in name:
            val = field.get("answer") or field.get("value") or ""
            txt = str(val).strip()
            if txt:
                return txt

    # 2. Repli sur le champ historique "Compétition concernée"
    if not fallback:
        return ""
    for field in item.get("customFields") or []:
        name = normalize_string(field.get("name") or "")
        if "competition" in name and "concerne" in name:
            val = field.get("answer") or field.get("value") or ""
            txt = str(val).strip()
            if txt:
                return txt
    return ""


def extract_competition_name(item: dict) -> str:
    """Extrait la valeur du champ personnalisé « Compétition concernée » de l'item.

    Champ texte libre où l'adhérent décrit la compétition visée (ex : « Coupe
    régionale de bloc Ambérieu »). Comme partout dans le projet, la réponse peut
    résider dans `answer` ou `value`.
    """
    for field in item.get("customFields") or []:
        name = normalize_string(field.get("name") or "")
        if "competition" in name and "concerne" in name:
            val = field.get("answer") or field.get("value") or ""
            txt = str(val).strip()
            if txt:
                return txt
    return ""


def competition_number_ok(valeur_champ: str, no_competition: str) -> bool:
    """Vrai si le contrôle du n° d'épreuve est satisfait (ou désactivé).

    - no_competition vide : contrôle désactivé (n° d'épreuve non renseigné en base) ;
    - sinon le n° attendu doit apparaître dans la valeur saisie par l'adhérent
      (comparaison normalisée : minuscules, sans accents, espaces neutralisés).
    """
    expected = normalize_string(no_competition)
    if not expected:
        return True
    return expected in normalize_string(valeur_champ)


def summarize_items(items: list) -> list:
    """Projection tabulaire des articles HelloAsso pour affichage / miroir local.

    Les n° de licence et de compétition restent **à vide** lorsque l'adhérent ne
    les a pas saisis sur le formulaire (consigne métiier : ne rien inventer).
    """
    rows = []
    for item in items or []:
        rows.append({
            "id_item": item.get("id"),
            "payeur": _item_payer_name(item),
            "montant": _item_amount(item),
            "commande": str((item.get("order") or {}).get("id") or ""),
            "licence": extract_licence(item),
            "competition": extract_competition_number(item),
            "etat": str(item.get("state") or ""),
            "date_item": _item_date(item),
        })
    return rows


def _item_date(item: dict) -> str:
    """Date de l'article : un article HelloAsso n'a pas de date propre, on prend
    celle de la commande (ou du premier paiement)."""
    if item.get("date"):
        return str(item.get("date"))
    order = item.get("order") or {}
    if order.get("date"):
        return str(order.get("date"))
    for p in item.get("payments") or []:
        if isinstance(p, dict) and p.get("date"):
            return str(p.get("date"))
    return ""


def link_source(value) -> str:
    """Source d'un lien existant, que l'appelant passe {id: source} ou {id: {..., source}}."""
    if isinstance(value, dict):
        return str(value.get("source") or "")
    return str(value or "")


# Lignes que le moteur automatique ne doit jamais toucher
SOURCES_FIGEES = ("manuel", "ignore")


def match_adherent_by_name(payer: str, adherents: list):
    """Retrouve un adhérent par nom + prénom (normalisés ; ordre des mots inversé accepté).

    - payer : « NOM Prénom » tel que saisi par le payeur sur HelloAsso ;
    - adherents : [{id, nom, prenom}] (instantané local).
    Retourne l'id de l'adhérent ou None si aucun rapprochement exact.
    """
    key = normalize_name(payer)
    if not key:
        return None
    keys = {key}
    parts = key.split()
    if len(parts) == 2:
        keys.add(" ".join(reversed(parts)))
    for a in adherents or []:
        full = normalize_name(f"{a.get('nom')} {a.get('prenom')}")
        if full in keys:
            return a.get("id")
    return None


def _index_competitions(competitions: list) -> tuple[dict[str, dict], list[tuple[str, dict]]]:
    """Correspondance champ saisi -> compétition : égalité exacte d'abord, puis
    « contient » (du n° le plus long au plus court pour privilégier la précision)."""
    comps_exact: dict[str, dict] = {}
    comps_contains: list[tuple[str, dict]] = []
    for competition in competitions or []:
        ref = normalize_string(competition.get("id_ffme") or "")
        if not ref:
            continue
        comps_exact.setdefault(ref, competition)
        comps_contains.append((ref, competition))
    comps_contains.sort(key=lambda rc: len(rc[0]), reverse=True)
    return comps_exact, comps_contains


def _find_competition(saisie: str, comps_exact: dict[str, dict], comps_contains: list[tuple[str, dict]]) -> Optional[dict]:
    if not saisie:
        return None
    competition = comps_exact.get(saisie)
    if competition is not None:
        return competition
    return next((c for ref, c in comps_contains if ref in saisie), None)


def _find_item_adherent(item: dict, by_licence: dict[str, dict], adherents: list) -> Optional[dict]:
    """Adhérent d'un article : par n° de licence, puis par nom du payeur."""
    licence = re.sub(r"\D", "", str(item.get("licence") or ""))
    adherent = by_licence.get(licence) if licence else None
    if adherent is not None:
        return adherent
    payer_id = match_adherent_by_name(item.get("payeur") or "", adherents)
    return next((a for a in adherents if a.get("id") == payer_id), None)


def auto_link_items(items: list, competitions: list, adherents: list,
                    existing_links: Optional[dict] = None) -> dict:
    """Calcule les liens automatiques article → (compétition, adhérent).

    - items : projection du miroir (summarize_items) ;
    - competitions : [{id, id_ffme, nom}] ;
    - adherents : [{id, num_licence, nom, prenom}] (instantané local) ;
    - existing_links : {id_item: source} ou {id_item: {..., "source"}} — les liens
      'manuel' et les lignes ignorées ('ignore') ne sont jamais recalculés.

    La compétition provient du champ « Compétition concernée » (n° d'épreuve saisi) :
    sans champ exploitable, l'article n'est PAS lié automatiquement (il reste
    « à rattacher » manuellement). L'adhérent est déduit par n° de licence puis
    par nom normalisé (peut rester NULL si inconnu).
    Retourne {id_item: {"competition_id": int, "adherent_id": int|None, "source": "auto"}}.
    """
    existing_links = existing_links or {}
    by_licence: dict[str, dict] = {}
    for a in adherents or []:
        lic = re.sub(r"\D", "", str(a.get("num_licence") or ""))
        if lic:
            by_licence.setdefault(lic, a)

    comps_exact, comps_contains = _index_competitions(competitions)

    links = {}
    for it in items or []:
        id_item = it.get("id_item")
        if id_item is None:
            continue
        if link_source(existing_links.get(id_item)) in SOURCES_FIGEES:
            continue
        if normalize_string(it.get("etat") or "") not in STATUTS_PAYES:
            continue

        comp = _find_competition(normalize_string(it.get("competition") or ""), comps_exact, comps_contains)
        if comp is None:
            continue  # compétition inconnue : rattachement manuel requis

        adherent = _find_item_adherent(it, by_licence, adherents or [])

        links[id_item] = {
            "competition_id": comp.get("id"),
            "adherent_id": adherent.get("id") if adherent else None,
            "source": "auto",
        }
    return links


def _item_state(item: dict) -> str:
    return str(item.get("state") or "").strip().lower()


def _item_amount(item: dict) -> float:
    try:
        return round(float(item.get("amount") or 0) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def _item_payer_name(item: dict) -> str:
    user = item.get("user") or {}
    first = str(user.get("firstName") or "").strip()
    last = str(user.get("lastName") or "").strip()
    return f"{last} {first}".strip()


def _anomaly(kind: str, severite: str, titre: str, detail: str) -> dict:
    return {"type": kind, "severite": severite, "titre": titre, "detail": detail}


class ItemPayment(NamedTuple):
    """The fields of a HelloAsso item the matching reads, read once."""
    state: str
    amount: float
    licence: str
    payer: str
    order_ref: str


def _item_payment(item: dict) -> ItemPayment:
    return ItemPayment(state=_item_state(item), amount=_item_amount(item), licence=extract_licence(item),
                       payer=_item_payer_name(item), order_ref=str((item.get("order") or {}).get("id") or ""))


class ParticipantIndex(NamedTuple):
    """Participants by licence number and by normalised name (the first one wins)."""
    by_licence: dict[str, dict]
    by_name: dict[str, dict]


def _index_participants(participants: list) -> ParticipantIndex:
    """Index des participants par licence puis par nom normalisé (premier gagnant)."""
    by_licence: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for participant in participants:
        licence = re.sub(r"\D", "", str(participant.get("num_licence") or ""))
        if licence:
            by_licence.setdefault(licence, participant)
        key = normalize_name(f"{participant.get('nom')} {participant.get('prenom')}")
        if key:
            by_name.setdefault(key, participant)
    return ParticipantIndex(by_licence, by_name)


def _unpaid_status_anomaly(payment: ItemPayment) -> Optional[dict]:
    """Anomalie d'un article non payé (remboursé, non finalisé), None s'il est payé."""
    payer, amount, order_ref, state = payment.payer, payment.amount, payment.order_ref, payment.state
    if state == "refunded":
        return _anomaly("remboursement", "info", "Paiement remboursé",
                        f"{payer or 'Inconnu'} ({amount:.2f} €, commande {order_ref}) est remboursé sur HelloAsso.")
    if state not in STATUTS_PAYES:
        return _anomaly("paiement_non_finalise", "info", "Paiement non finalisé",
                        f"{payer or 'Inconnu'} ({amount:.2f} €, commande {order_ref}) : "
                        f"statut HelloAsso « {state or 'inconnu'} ».")
    return None


def _manual_review_entry(item: dict, payment: ItemPayment, valeur_champ: str, no_competition: str,
                         index: ParticipantIndex) -> tuple[dict, dict]:
    """Paiement au n° d'épreuve absent ou non conforme : (ligne de correction manuelle, anomalie)."""
    payer, order_ref, licence = payment.payer, payment.order_ref, payment.licence
    participant = (index.by_licence.get(licence) if licence else None) or index.by_name.get(normalize_name(payer))
    if valeur_champ:
        anomaly = _anomaly("competition_ecartee", "avertissement", "N° de compétition non conforme",
                           f"{payer or 'Inconnu'} (commande {order_ref}) : le champ « Compétition concernée » "
                           f"indique « {valeur_champ} » au lieu du n° attendu « {no_competition} » ; "
                           f"validation manuelle requise.")
    else:
        anomaly = _anomaly("competition_manquante", "avertissement", "N° de compétition absent sur HelloAsso",
                           f"{payer or 'Inconnu'} (commande {order_ref}) : le champ « Compétition concernée » "
                           f"n'est pas renseigné sur HelloAsso ; validation manuelle requise.")
    entry = {
        "payer": payer or "Inconnu",
        "montant": payment.amount,
        "etat": str(item.get("state") or ""),
        "date_item": str(item.get("date") or ""),
        "order_ref": order_ref,
        "licence": licence,
        "valeur_champ": valeur_champ,
        "competition_concernee": extract_competition_name(item),
        "numero_competition": extract_competition_number(item, fallback=False),
        "adherent_id": participant.get("adherent_id") if participant else None,
        "participant": f"{participant.get('nom')} {participant.get('prenom')}" if participant else "",
    }
    return entry, anomaly


def _find_paying_participant(payment: ItemPayment, index: ParticipantIndex) -> tuple[Optional[dict], Optional[dict]]:
    """(participant, anomalie) d'un paiement : par licence, sinon par nom (avec une anomalie de rapprochement)."""
    payer, order_ref, licence = payment.payer, payment.order_ref, payment.licence
    if licence:
        participant = index.by_licence.get(licence)
        if participant is not None:
            return participant, None
        # Licence renseignée mais inconnue : tenter un rapprochement par nom en secours
        participant = index.by_name.get(normalize_name(payer))
        if participant:
            return participant, _anomaly(
                "licence_ecartee", "avertissement", "Licence non reconnue",
                f"{payer} (commande {order_ref}) : le n° de licence « {licence} » ne correspond "
                f"à aucun participant ; rapproché par le nom (licence attendue : "
                f"{participant.get('num_licence') or 'absente'}).")
        return participant, None
    participant = index.by_name.get(normalize_name(payer))
    if participant:
        return participant, _anomaly(
            "paiement_sans_licence", "avertissement", "Paiement sans n° de licence",
            f"{payer} (commande {order_ref}) : aucun champ « licence » valide sur HelloAsso ; "
            f"rapproché par le nom (licence attendue : {participant.get('num_licence') or 'absente'}).")
    return participant, None


def _pending_count_and_missing_payments(participants: list, seen_participants: dict) -> tuple[int, list[dict]]:
    """Participants sélectionnés restés sans paiement (relance), et une anomalie par « Payé » sans paiement HelloAsso."""
    pending_count = 0
    anomalies: list[dict] = []
    for participant in participants:
        if not participant.get("selectionne"):
            continue
        if participant.get("statut_paiement") == PAIEMENT_PAYE and participant.get("adherent_id") not in seen_participants:
            # Déjà marqué payé en base sans paiement détecté sur cette campagne : signaler
            anomalies.append(_anomaly("paiement_absent", "avertissement", "Payé en base sans paiement HelloAsso",
                                      f"{participant.get('nom')} {participant.get('prenom')} est marqué « Payé » dans "
                                      f"la base mais aucun paiement correspondant n'a été trouvé sur la campagne."))
        elif participant.get("statut_paiement") != PAIEMENT_PAYE:
            pending_count += 1
    return pending_count, anomalies


def match_items_to_participants(items: list, participants: list, prix_attendu: Optional[float] = None,
                                no_competition: str = "") -> dict:
    """Croise les articles HelloAsso avec les participants de la compétition.

    - items : liste brute API (chaque item = un article vendu) ;
    - participants : dicts {adherent_id, nom, prenom, num_licence, statut_paiement, montant_paye} ;
    - prix_attendu : tarif d'inscription de la compétition (détection d'écart) ;
    - no_competition : n° d'épreuve attendu dans le champ « Compétition concernée » du
      formulaire HelloAsso (id_ffme de la compétition). Contrôle désactivé si vide.

    Retourne {
      "updates":          [(adherent_id, montant_paye), ...]        # à marquer « paye »
      "order_by_adherent": {adherent_id: "n° commande (, n°…)"}     # pour affichage
      "manual_review":    [{payer, montant, etat, date_item, order_ref, licence,
                             valeur_champ, competition_concernee, numero_competition,
                             adherent_id, participant}, ...]  # correction manuelle proposée
      "anomalies":        [{"type", "severite", "titre", "detail"}] # rapport d'écarts
      "stats":            {nb_items, nb_payes, nb_matchs, nb_en_attente, nb_anomalies,
                           nb_manual_review}
    }
    """
    updates = []
    order_by_adherent = {}
    manual_review = []
    anomalies: list[dict] = []
    index = _index_participants(participants)
    seen_participants: dict = {}
    nb_payes = 0

    for item in items or []:
        if _item_state(item) in ("canceled", "cancelled"):
            continue
        payment = _item_payment(item)
        amount, licence, payer, order_ref = payment.amount, payment.licence, payment.payer, payment.order_ref

        unpaid = _unpaid_status_anomaly(payment)
        if unpaid is not None:
            anomalies.append(unpaid)
            continue

        nb_payes += 1

        # Contrôle du n° d'épreuve (champ « Compétition concernée » du formulaire) :
        # absent ou non conforme -> PAS de passage automatique à « Payé », le paiement
        # part en correction manuelle (avec la valeur saisie sur HelloAsso en aide).
        valeur_champ = extract_competition_number(item)
        if not competition_number_ok(valeur_champ, no_competition):
            entry, anomaly = _manual_review_entry(item, payment, valeur_champ, no_competition, index)
            anomalies.append(anomaly)
            manual_review.append(entry)
            continue

        participant, match_anomaly = _find_paying_participant(payment, index)
        if match_anomaly is not None:
            anomalies.append(match_anomaly)
        if participant is None:
            anomalies.append(_anomaly("paiement_inconnu", "erreur", "Paiement non identifié",
                                      f"Paiement reçu ({amount:.2f} €, commande {order_ref}) pour « {payer or 'inconnu'} » "
                                      f"{'(licence ' + licence + ') ' if licence else ''}sans participant correspondant "
                                      f"({normalize_name(payer) or 'sans nom'})."))
            continue

        adherent_id = participant.get("adherent_id")
        nom_complet = f"{participant.get('nom')} {participant.get('prenom')}"
        previous = seen_participants.get(adherent_id)
        if previous is not None:
            anomalies.append(_anomaly("doublon", "erreur", "Plusieurs paiements",
                                      f"{nom_complet} : plusieurs paiements détectés (commandes {previous} et {order_ref}). "
                                      f"Vérifier sur HelloAsso (remboursement / double inscription ?)."))
            seen_participants[adherent_id] = f"{previous}, {order_ref}"
            order_by_adherent[adherent_id] = seen_participants[adherent_id]
            updates.append((adherent_id, amount))
            continue
        seen_participants[adherent_id] = order_ref

        if prix_attendu is not None and prix_attendu > 0 and abs(amount - float(prix_attendu)) > 0.01:
            anomalies.append(_anomaly("ecart_tarif", "avertissement", "Écart de tarif",
                                      f"{nom_complet} : {amount:.2f} € payés contre {float(prix_attendu):.2f} € attendus "
                                      f"(commande {order_ref})."))

        order_by_adherent[adherent_id] = order_ref
        updates.append((adherent_id, amount))

    nb_en_attente, missing_payments = _pending_count_and_missing_payments(participants, seen_participants)
    anomalies.extend(missing_payments)

    return {
        "updates": updates,
        "order_by_adherent": order_by_adherent,
        "manual_review": manual_review,
        "anomalies": anomalies,
        "stats": {
            "nb_items": len(items or []),
            "nb_payes": nb_payes,
            "nb_matchs": len({u[0] for u in updates}),
            "nb_en_attente": nb_en_attente,
            "nb_anomalies": len(anomalies),
            "nb_manual_review": len(manual_review),
        },
    }
