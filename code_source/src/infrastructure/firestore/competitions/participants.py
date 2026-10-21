"""Participants: the array embedded in each competition document, written under an
optimistic lock (re-read and replayed on conflict)."""
from typing import Callable, Dict, Any, List, Optional, Tuple

from domain.competitions.models import (
    Participant,
    PAIEMENT_EN_ATTENTE,
    PAIEMENT_NON_INVITE,
    PAIEMENT_ANNULE_PERDU,
    PAIEMENT_PAYE,
    PAIEMENT_STATUTS_ANNULES,
    statut_paiement_apres_bascule,
)
from infrastructure.firestore.competitions.adherents import AdherentsMixin

# Collé pour l'ancien appelant (web) : état de paiement par défaut d'un nouveau
# participant ajouté explicitement (même sémantique que l'ancienne base SQLite).
DEFAULT_STATUT_NOUVEAU_PARTICIPANT = PAIEMENT_EN_ATTENTE

# Order reference of a payment recorded by hand on the bureau page (cheque, cash)
MANUAL_PAYMENT_REF = "Règlement manuel"


class ParticipantAlreadyPaid(Exception):
    """Unselecting a participant who already paid requires the coach's cancellation
    decision (money lost or carried over), not a plain toggle."""


class ParticipantChanged(Exception):
    """The participant row changed since the client read it (its `updated_at` differs): a
    change queued offline is refused rather than overwrite a newer one (plan phase 5b)."""


# Row guard of _update_participant: False leaves the row as it is, an exception refuses the write
RowGuard = Callable[[Dict[str, Any]], bool]


def unchanged_since_guard(field: str, value: bool, seen_updated_at: Optional[str]) -> Optional[RowGuard]:
    """Guard of a flag change sent with the row's `updated_at` the client saw. Flag already at
    `value`: nothing to write (so a replayed request is harmless). Otherwise the row must not
    have changed since: ParticipantChanged. None (no guard) when `seen_updated_at` is None."""
    if seen_updated_at is None:
        return None

    def guard(p: Dict[str, Any]) -> bool:
        if bool(p.get(field)) == bool(value):
            return False
        if str(p.get("updated_at") or "") != seen_updated_at:
            raise ParticipantChanged(field)
        return True
    return guard


class ParticipantsMixin(AdherentsMixin):
    """Participant rows of a competition; new rows are copied from the member directory."""

    # ------------------------------------------------------------------
    # Participants (tableau embarqué dans le document de l'épreuve)
    # ------------------------------------------------------------------
    @classmethod
    def list_participants(cls, competition_id: int, selected_only: bool = False) -> List[Participant]:
        doc = cls._load_comp_doc(competition_id)
        if not doc:
            return []
        parts = doc.get("participants") or []
        if selected_only:
            parts = [p for p in parts if p.get("selectionne")]
        adh = cls._adherent_map()
        result = []
        for p in parts:
            row = dict(p)
            a = adh.get(p.get("adherent_id")) or {}
            row.setdefault("tarif", a.get("tarif") or "")
            row.setdefault("email", a.get("email") or "")
            row.setdefault("nom", a.get("nom") or "")
            row.setdefault("prenom", a.get("prenom") or "")
            row.setdefault("num_licence", a.get("num_licence") or "")
            row.setdefault("date_synchro_helloasso", row.get("updated_at") or "")
            row["competition_id"] = competition_id
            result.append(Participant.from_row(row))
        result.sort(key=lambda p: ((p.nom or "").lower(), (p.prenom or "").lower()))
        return result

    @classmethod
    def _new_participant_map(cls, adherent_doc: Dict[str, Any],
                             selectionne: bool, statut: Optional[str] = None) -> Dict[str, Any]:
        stat = statut or (DEFAULT_STATUT_NOUVEAU_PARTICIPANT if selectionne else PAIEMENT_NON_INVITE)
        return {
            "participant_id": adherent_doc.get("id"),
            "adherent_id": adherent_doc.get("id"),
            "nom": str(adherent_doc.get("nom") or "").upper(),
            "prenom": str(adherent_doc.get("prenom") or ""),
            "num_licence": str(adherent_doc.get("licence_ffme") or adherent_doc.get("num_licence") or ""),
            "email": str(adherent_doc.get("email") or ""),
            "phone": str(adherent_doc.get("phone") or ""),
            "tarif": str(adherent_doc.get("tarif") or ""),
            "selectionne": bool(selectionne),
            "statut_paiement": stat,
            "montant_paye": 0.0,
            "commande_helloasso": "",
            "note_paiement": "",
            "urgence_nom": str(adherent_doc.get("emergency_name") or ""),
            "urgence_tel": str(adherent_doc.get("emergency_phone") or ""),
            "updated_at": cls._now_iso(),
        }

    @classmethod
    def _new_participant(cls, adherent_id: int, selectionne: bool) -> Dict[str, Any]:
        """New participant row for a member, copied from the `adherents` directory."""
        adh = cls._adherent_map().get(adherent_id) or {"id": adherent_id}
        return cls._new_participant_map(adh, selectionne)

    @classmethod
    def _mutate_participants(cls, competition_id: int, mutate) -> Optional[Dict[str, Any]]:
        """Charge le document, applique `mutate(parts)`, réécrit le tableau.

        `mutate` peut renvoyer None pour signaler « rien à faire » : aucune
        écriture n'a alors lieu.

        Verrouillage optimiste : l'écriture n'est acceptée que si le document n'a
        pas changé depuis sa lecture. En cas de conflit, le document est relu et
        `mutate` ré-appliqué sur la version à jour (jusqu'à `_MAX_WRITE_ATTEMPTS`
        fois). `mutate` doit donc pouvoir être rejoué : il ne dépend que de la
        liste reçue. Le document renvoyé contient les participants écrits."""
        def attempt():
            doc = cls._load_comp_doc(competition_id)
            if not doc:
                return None
            parts = [dict(p) for p in (doc.get("participants") or [])]
            new_parts = mutate(parts)
            if new_parts is None:
                return None
            doc.update(cls._save_parts(doc, new_parts))  # participants, counters, updated_at
            return doc
        return cls._with_retries(f"Épreuve #{competition_id}", attempt)

    @classmethod
    def _update_participant(cls, competition_id: int, adherent_id: int, change,
                            add_missing: Optional[bool] = None,
                            guard: Optional[RowGuard] = None) -> Optional[Dict[str, Any]]:
        """Applies `change(p)` to the member's participant row(s), stamping `updated_at`
        first (`change` may override it). `change` returns False to leave a row as it was.
        `guard(p)` sees the row before the stamp: False skips it, an exception refuses the
        write (checked again on every retry of the optimistic lock).

        Member not listed: a new row is added with `selectionne=add_missing`, or nothing is
        written when `add_missing` is None. Returns the written document, or None when
        nothing was written (unknown competition, member not listed, nothing changed)."""
        def mutate(parts):
            found = changed = False
            for p in parts:
                if p.get("adherent_id") != adherent_id:
                    continue
                found = True
                if guard is not None and not guard(p):
                    continue
                before = dict(p)
                p["updated_at"] = cls._now_iso()
                if change(p) is False:
                    p.clear()
                    p.update(before)
                else:
                    changed = True
            if not found and add_missing is not None:
                parts.append(cls._new_participant(adherent_id, add_missing))
                changed = True
            return parts if changed else None
        return cls._mutate_participants(competition_id, mutate)

    # The *_doc writes below return the competition document as written (None: unknown
    # competition, or member not listed where that applies); see competition_api_doc.
    @classmethod
    def add_participant_doc(cls, competition_id: int, adherent_id: int,
                            selectionne: bool = True) -> Optional[Dict[str, Any]]:
        def change(p):
            if selectionne:
                p["selectionne"] = True
                if (p.get("statut_paiement") or "") in PAIEMENT_STATUTS_ANNULES:
                    p["statut_paiement"] = PAIEMENT_PAYE   # réactivation : l'argent est déjà là
        return cls._update_participant(competition_id, adherent_id, change, add_missing=selectionne)

    @classmethod
    def add_participant(cls, competition_id: int, adherent_id: int,
                        selectionne: bool = True) -> int:
        """Ajoute un adhérent à une compétition (idempotent) ; retourne l'identifiant
        de la ligne participant (existante ou nouvelle)."""
        doc = cls.add_participant_doc(competition_id, adherent_id, selectionne)
        if doc is None:
            return 0
        for p in doc.get("participants") or []:
            if p.get("adherent_id") == adherent_id:
                return p.get("participant_id") or adherent_id
        return adherent_id

    @classmethod
    def remove_participant_doc(cls, competition_id: int, adherent_id: int) -> Optional[Dict[str, Any]]:
        def mutate(parts):
            kept = [p for p in parts if p.get("adherent_id") != adherent_id]
            return kept if len(kept) != len(parts) else None
        return cls._mutate_participants(competition_id, mutate)

    @classmethod
    def remove_participant(cls, competition_id: int, adherent_id: int) -> bool:
        return cls.remove_participant_doc(competition_id, adherent_id) is not None

    @classmethod
    def set_selection(cls, competition_id: int, adherent_id: int, selectionne: bool,
                      refuse_unselect_paid: bool = False) -> bool:
        cls.set_selection_doc(competition_id, adherent_id, selectionne, refuse_unselect_paid)
        return True

    @classmethod
    def set_selection_doc(cls, competition_id: int, adherent_id: int, selectionne: bool,
                          refuse_unselect_paid: bool = False,
                          unchanged_since: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """`refuse_unselect_paid`: raise ParticipantAlreadyPaid instead of unselecting a
        participant who paid (checked on the fresh document, so a payment recorded
        meanwhile by the webhook is seen). `unchanged_since`: see unchanged_since_guard; the
        member must then be listed already. None: unknown competition, member not listed
        where that applies, or nothing to change."""
        def change(p):
            if (refuse_unselect_paid and not selectionne
                    and (p.get("statut_paiement") or "") == PAIEMENT_PAYE):
                raise ParticipantAlreadyPaid(adherent_id)
            p["selectionne"] = bool(selectionne)
            nouveau = statut_paiement_apres_bascule(p.get("statut_paiement"), selectionne)
            if nouveau:
                p["statut_paiement"] = nouveau
        guard = unchanged_since_guard("selectionne", selectionne, unchanged_since)
        return cls._update_participant(competition_id, adherent_id, change,
                                       add_missing=selectionne if guard is None else None, guard=guard)

    @classmethod
    def set_present_doc(cls, competition_id: int, adherent_id: int, present: bool,
                        unchanged_since: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Attendance flag (pass-through field of the bureau page, appendix B of the plan).
        `unchanged_since`: see unchanged_since_guard."""
        return cls._update_participant(competition_id, adherent_id,
                                       lambda p: p.update(present=bool(present)),
                                       guard=unchanged_since_guard("present", present, unchanged_since))

    @classmethod
    def set_present(cls, competition_id: int, adherent_id: int, present: bool) -> bool:
        return cls.set_present_doc(competition_id, adherent_id, present) is not None

    @classmethod
    def set_payment_status(cls, competition_id: int, adherent_id: int, statut_paiement: str) -> bool:
        return cls._update_participant(competition_id, adherent_id,
                                       lambda p: p.update(statut_paiement=statut_paiement)) is not None

    @classmethod
    def record_manual_payment_doc(cls, competition_id: int, adherent_id: int,
                                  montant: float) -> Optional[Dict[str, Any]]:
        """Payment received outside HelloAsso (cheque, cash): the participant is selected and
        paid. None when the member is not listed on the competition."""
        def change(p):
            p.update(selectionne=True, statut_paiement=PAIEMENT_PAYE,
                     montant_paye=float(montant), commande_helloasso=MANUAL_PAYMENT_REF)
        return cls._update_participant(competition_id, adherent_id, change)

    @classmethod
    def record_manual_payment(cls, competition_id: int, adherent_id: int, montant: float) -> bool:
        return cls.record_manual_payment_doc(competition_id, adherent_id, montant) is not None

    @classmethod
    def mark_cancelled(cls, competition_id: int, adherent_id: int,
                       statut_annulation: str, note: str = "") -> bool:
        return cls.mark_cancelled_doc(competition_id, adherent_id, statut_annulation, note) is not None

    @classmethod
    def mark_cancelled_doc(cls, competition_id: int, adherent_id: int,
                           statut_annulation: str, note: str = "") -> Optional[Dict[str, Any]]:
        """Annule la participation d'un compétiteur ayant payé.

        - `statut_annulation` : 'annule_perdu' (argent encaissé définitivement)
          ou 'annule_reporte' (crédit pour une prochaine épreuve) ;
        - le montant payé reste comptabilisé sur l'épreuve ;
        - un commentaire explicatif est enregistré (note_paiement)."""
        if statut_annulation not in PAIEMENT_STATUTS_ANNULES:
            statut_annulation = PAIEMENT_ANNULE_PERDU

        def change(p):
            p["selectionne"] = False
            p["statut_paiement"] = statut_annulation
            if note:
                p["note_paiement"] = str(note)
        return cls._update_participant(competition_id, adherent_id, change)

    @classmethod
    def apply_helloasso_payment(cls, competition_id: int, adherent_id: int,
                                montant_paye: float, date_synchro: str = "",
                                order_ref: str = "") -> bool:
        date_val = date_synchro or cls._now_display()
        def change(p):
            if (p.get("statut_paiement") or "") in PAIEMENT_STATUTS_ANNULES:
                # Annulation explicite du coach : la re-synchronisation
                # HelloAsso ne doit pas l'écraser.
                return False
            p["statut_paiement"] = PAIEMENT_PAYE
            p["montant_paye"] = float(montant_paye or 0.0)
            p["commande_helloasso"] = str(order_ref or "")
            p["updated_at"] = date_val
        return cls._update_participant(competition_id, adherent_id, change) is not None

    @classmethod
    def load_competition_group_into(cls, competition_id: int) -> int:
        """Pré-remplit la liste des participants avec le groupe « Compétition »."""
        return cls.load_competition_group_doc(competition_id)[0]

    @classmethod
    def load_competition_group_doc(cls, competition_id: int) -> Tuple[int, Optional[Dict[str, Any]]]:
        """(number added, document written); the document is None when nobody was added."""
        groupe = cls.list_adherents(competition_only=True)
        added = {"count": 0}

        def mutate(parts):
            existing = {p.get("adherent_id") for p in parts}
            now = cls._now_iso()
            added["count"] = 0
            for a in groupe:
                if a["id"] in existing:
                    continue
                p = cls._new_participant_map(a, False, PAIEMENT_NON_INVITE)
                p["updated_at"] = now
                parts.append(p)
                added["count"] += 1
            return parts if added["count"] else None
        doc = cls._mutate_participants(competition_id, mutate)
        return (added["count"], doc) if doc is not None else (0, None)
