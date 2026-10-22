"""Response models of the competition reads (the Vue competitions screen, frontend/src/pages/CompetitionsPage.vue).

The routes build their body by hand (json_with_etag): these models are the contract the frontend's types are
generated from, checked against real bodies by the tests. Competition documents are returned as stored: fields
older documents may miss have a default, and the stored fields not listed here (pass-through fields of the office
page, legacy coach slots, counters) are allowed."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CompetitionParticipant(BaseModel):
    """A member registered for a competition (row of its `participants`, infrastructure/firestore/competitions)."""
    model_config = ConfigDict(extra="allow")

    adherent_id: Optional[int] = None
    nom: str = ""
    prenom: str = ""
    num_licence: str = ""
    tarif: str = ""
    phone: str = ""
    selectionne: bool = False
    statut_paiement: str = Field("", description="non_invite, en_attente, paye, annule_perdu or annule_reporte")
    montant_paye: float = 0.0
    commande_helloasso: str = ""
    note_paiement: str = ""
    urgence_nom: str = Field("", description="Emergency contact copied when the member was added")
    urgence_tel: str = ""
    classement: str = ""
    resultat_ffme: str = ""
    updated_at: str = ""


class Competition(BaseModel):
    """A competition with its participants, most recent first in the list."""
    model_config = ConfigDict(extra="allow")

    id: int
    nom: str = ""
    id_ffme: str = ""
    date_competition: str = Field("", description="YYYY-MM-DD, empty when not dated")
    date_fin: str = ""
    prix: float = 0.0
    statut: str = Field("en_preparation", description="en_preparation, en_cours or close (archived)")
    whatsapp_link: str = ""
    url_resultats: str = ""
    resultats_synced_at: str = ""
    coach_ids: List[int] = Field(default_factory=list)
    coaches: List[str] = Field(default_factory=list, description="Names of coach_ids, from the coaches collection")
    participants: List[CompetitionParticipant] = Field(default_factory=list)


class CompetitionMember(BaseModel):
    """A member of the `adherents` directory as the competition pages see it (current tariff and slot group)."""
    model_config = ConfigDict(extra="allow")

    id: Optional[int] = None
    nom: str = ""
    prenom: str = ""
    num_licence: str = ""
    tarif: str = ""
    saison: str = ""
    creneau_groupe: str = ""
