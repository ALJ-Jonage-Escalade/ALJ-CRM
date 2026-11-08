"""
Modèles métier du module de gestion des compétitions (base partagée Firestore).

Ces modèles sont purs (aucune dépendance réseau ni stockage) : réutilisables par
les services, le serveur web et les tests unitaires.
"""
import datetime
from dataclasses import dataclass, field
from typing import Any, List, Mapping

# Statuts possibles d'une compétition (cycle de vie)
STATUT_EN_PREPARATION = "en_preparation"
STATUT_EN_COURS = "en_cours"
STATUT_CLOSE = "close"
STATUTS_COMPETITION = (STATUT_EN_PREPARATION, STATUT_EN_COURS, STATUT_CLOSE)

# Coach slots of documents written before plan cleanup C2 (no `coach_ids` field): still read, never written.
LEGACY_COACH_SLOTS = ("coach1_id", "coach2_id", "coach3_id")


def coach_ids_of(row: Mapping[str, Any]) -> List[int]:
    """Ordered, distinct coach ids of a stored competition: `coach_ids`, or the legacy slots `coach1_id..coach3_id`
    of a document written before it existed (an empty `coach_ids` means no coach: stale slots are ignored)."""
    if row.get("coach_ids") is not None:
        raw = row["coach_ids"]
    else:
        raw = [row.get(slot) for slot in LEGACY_COACH_SLOTS]
    ids: List[int] = []
    for cid in raw:
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            continue
        if cid not in ids:
            ids.append(cid)
    return ids


LIBELLES_STATUT_COMPETITION = {
    STATUT_EN_PREPARATION: "En préparation",
    STATUT_EN_COURS: "En cours",
    STATUT_CLOSE: "Archivée",
}

# Statuts de paiement d'un participant
PAIEMENT_NON_INVITE = "non_invite"
PAIEMENT_EN_ATTENTE = "en_attente"
PAIEMENT_PAYE = "paye"
# Annulation d'un participant ayant payé : jamais de remboursement.
# - perdu : l'argent est encaissé définitivement (pas de crédit) ;
# - report : l'argent reste comptabilisé -> crédit visible au bilan de la saison,
#   qui compensera la prochaine épreuve de l'athlète.
PAIEMENT_ANNULE_PERDU = "annule_perdu"
PAIEMENT_ANNULE_REPORTE = "annule_reporte"
STATUTS_PAIEMENT = (
    PAIEMENT_NON_INVITE, PAIEMENT_EN_ATTENTE, PAIEMENT_PAYE,
    PAIEMENT_ANNULE_PERDU, PAIEMENT_ANNULE_REPORTE,
)

LIBELLES_STATUT_PAIEMENT = {
    PAIEMENT_NON_INVITE: "Non invité",
    PAIEMENT_EN_ATTENTE: "En attente",
    PAIEMENT_PAYE: "Payé",
    PAIEMENT_ANNULE_PERDU: "Annulé — perdu",
    PAIEMENT_ANNULE_REPORTE: "Annulé — report",
}

# Statuts « payé » réellement encaissés (money in) — l'annulation reportée
# garde l'argent côté club mais ne compte plus comme participation due.
PAIEMENT_STATUTS_ANNULES = (PAIEMENT_ANNULE_PERDU, PAIEMENT_ANNULE_REPORTE)


def payment_status_after_toggle(statut_paiement: str, selectionne: bool):
    """Statut de paiement résultant de la bascule « Participe ».

    Règle : le paiement « payé » et les annulations ne sont JAMAIS modifiés par
    la bascule (décision du coach via l'IHM). Un participant non invité coché
    passe « en attente » ; un « en attente » décoché repasse « non invité » ;
    un participant annulé re-coché repasse « payé » (réactivation).
    Retourne le nouveau statut, ou None s'il n'y a rien à changer."""
    statut = str(statut_paiement or PAIEMENT_NON_INVITE)
    if selectionne:
        if statut == PAIEMENT_NON_INVITE:
            return PAIEMENT_EN_ATTENTE
        if statut in PAIEMENT_STATUTS_ANNULES:
            return PAIEMENT_PAYE
        return None
    if statut == PAIEMENT_EN_ATTENTE:
        return PAIEMENT_NON_INVITE
    return None

LIBELLE_VERS_STATUT_PAIEMENT = {v: k for k, v in LIBELLES_STATUT_PAIEMENT.items()}
LIBELLE_VERS_STATUT_COMPETITION = {v: k for k, v in LIBELLES_STATUT_COMPETITION.items()}


def default_deadline(date_competition: str) -> str:
    """Date limite d'inscription par défaut : 7 jours avant le début de la compétition (ISO AAAA-MM-JJ)."""
    try:
        start = datetime.date.fromisoformat(date_competition.strip()[:10])
    except ValueError:
        return ""
    return (start - datetime.timedelta(days=7)).isoformat()


@dataclass
class Competition:
    """Une épreuve de la saison (document Firestore `competitions/{id}`)."""
    id: int = None
    id_ffme: str = ""
    nom: str = ""
    date_competition: str = ""       # date de début, ISO AAAA-MM-JJ
    date_fin: str = ""               # date de fin ISO ; vide = même jour que le début
    deadline: str = ""               # date limite d'inscription ISO, saisie à la main ; vide = 7j avant le début (default_deadline)
    prix: float = 0.0                # tarif d'inscription en euros
    statut: str = STATUT_EN_PREPARATION
    created_at: str = ""
    updated_at: str = ""
    coach_ids: List[int] = field(default_factory=list)  # ordered, no length limit
    url_resultats: str = ""
    resultats_synced_at: str = ""
    whatsapp_link: str = ""          # Lien d'invitation au groupe WhatsApp de la compétition
    # Identifiant Firestore réel du document (peut différer de str(id) sur une
    # base héritée ; normalisé au premier chargement par le référentiel).
    doc_id: str = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "id_ffme": self.id_ffme,
            "nom": self.nom,
            "date_competition": self.date_competition,
            "date_fin": self.date_fin,
            "deadline": self.deadline,
            "prix": self.prix,
            "statut": self.statut,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "coach_ids": list(self.coach_ids),
            "url_resultats": self.url_resultats,
            "resultats_synced_at": self.resultats_synced_at,
            "whatsapp_link": self.whatsapp_link,
        }

    @classmethod
    def from_row(cls, row: dict) -> "Competition":
        return cls(
            id=row.get("id"),
            id_ffme=str(row.get("id_ffme") or ""),
            nom=str(row.get("nom") or ""),
            date_competition=str(row.get("date_competition") or ""),
            date_fin=str(row.get("date_fin") or ""),
            deadline=str(row.get("deadline") or "").strip(),
            prix=float(row.get("prix") or 0.0),
            statut=str(row.get("statut") or STATUT_EN_PREPARATION),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
            coach_ids=coach_ids_of(row),
            url_resultats=str(row.get("url_resultats") or ""),
            resultats_synced_at=str(row.get("resultats_synced_at") or ""),
            whatsapp_link=str(row.get("whatsapp_link") or ""),
            doc_id=row.get("doc_id") or row.get("_doc_id"),
        )


@dataclass
class Participant:
    """Lien entre un adhérent et une compétition (inscription + suivi du paiement)."""
    id: int = None
    competition_id: int = None
    adherent_id: int = None
    # Champs dénormalisés (copie adhérent pour affichage et export autonome) :
    nom: str = ""
    prenom: str = ""
    num_licence: str = ""
    email: str = ""
    tarif: str = ""
    selectionne: bool = False
    present: bool = False            # pointage sur place le jour de la compétition
    statut_paiement: str = PAIEMENT_NON_INVITE
    date_synchro_helloasso: str = ""
    montant_paye: float = 0.0
    commande_helloasso: str = ""     # n° de commande HelloAsso (renseigné à la synchro)
    note_paiement: str = ""          # commentaire du coach (annulation, régularisation…)
    classement: str = ""             # rang ou classement FFME (ex: "1", "4", "13")
    total_categorie: int = 0         # nombre total de compétiteurs dans la catégorie (ex: 14)
    resultat_ffme: str = ""          # libellé complet (ex: "6 / 14" ou "1er / 15")
    categorie_ffme: str = ""         # catégorie officielle MyCompet (ex: "U13Femme")
    performance_ffme: str = ""       # points ou score MyCompet
    resultat_synced_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "competition_id": self.competition_id,
            "adherent_id": self.adherent_id,
            "nom": self.nom,
            "prenom": self.prenom,
            "num_licence": self.num_licence,
            "email": self.email,
            "tarif": self.tarif,
            "selectionne": bool(self.selectionne),
            "present": bool(self.present),
            "statut_paiement": self.statut_paiement,
            "date_synchro_helloasso": self.date_synchro_helloasso,
            "montant_paye": self.montant_paye,
            "commande_helloasso": self.commande_helloasso,
            "note_paiement": self.note_paiement,
            "classement": self.classement,
            "total_categorie": self.total_categorie,
            "resultat_ffme": self.resultat_ffme,
            "categorie_ffme": self.categorie_ffme,
            "performance_ffme": self.performance_ffme,
            "resultat_synced_at": self.resultat_synced_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> "Participant":
        sel = row.get("selectionne")
        return cls(
            id=row.get("id"),
            competition_id=row.get("competition_id"),
            adherent_id=row.get("adherent_id"),
            nom=str(row.get("nom") or ""),
            prenom=str(row.get("prenom") or ""),
            num_licence=str(row.get("num_licence") or ""),
            email=str(row.get("email") or ""),
            tarif=str(row.get("tarif") or ""),
            selectionne=bool(sel) and str(sel) not in ("0", "Non", "non"),
            present=bool(row.get("present")),
            statut_paiement=str(row.get("statut_paiement") or PAIEMENT_NON_INVITE),
            date_synchro_helloasso=str(row.get("date_synchro_helloasso") or ""),
            montant_paye=float(row.get("montant_paye") or 0.0),
            commande_helloasso=str(row.get("commande_helloasso") or ""),
            note_paiement=str(row.get("note_paiement") or ""),
            classement=str(row.get("classement") or ""),
            total_categorie=int(row.get("total_categorie") or 0),
            resultat_ffme=str(row.get("resultat_ffme") or ""),
            categorie_ffme=str(row.get("categorie_ffme") or ""),
            performance_ffme=str(row.get("performance_ffme") or ""),
            resultat_synced_at=str(row.get("resultat_synced_at") or ""),
        )
