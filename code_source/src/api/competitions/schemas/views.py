"""Response models of the competition routes (the Vue competitions screen, frontend/src/pages/CompetitionsPage.vue).

The reads build their body by hand (json_with_etag): these models are the contract the frontend's types are
generated from, checked against real bodies by the tests. Competition documents are returned as stored: fields
older documents may miss have a default, and the stored fields not listed here (legacy coach slots, counters) are
allowed."""

from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from domain.members.sex import Sex


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
    email: str = Field("", description="Copied when the member was added")
    present: bool = Field(False, description="Checked in on the day of the competition")
    classement: str = ""
    total_categorie: Union[int, str] = 0
    categorie_ffme: str = ""
    resultat_ffme: str = ""
    sex: Optional[Sex] = Field(None, description="Read from the member (adherents directory), None when not given")
    updated_at: str = Field("", description="Sent back as unchanged_since by a change queued offline")


class Competition(BaseModel):
    """A competition with its participants, most recent first in the list."""
    model_config = ConfigDict(extra="allow")

    id: int
    nom: str = ""
    id_ffme: str = ""
    date_competition: str = Field("", description="YYYY-MM-DD, empty when not dated")
    date_fin: str = ""
    deadline: str = Field("", description="YYYY-MM-DD, registration deadline (defaults to 1 week before date_competition)")
    prix: float = 0.0
    statut: str = Field("en_preparation", description="en_preparation, en_cours or close (archived)")
    whatsapp_link: str = ""
    url_resultats: str = ""
    resultats_synced_at: str = ""
    # Pass-through fields of the office page (plan_api_only_front.md appendix B): stored as given
    lieu: Optional[str] = None
    type: Optional[str] = None
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
    licence_ffme: str = ""
    email: str = ""
    email_secondaire: str = ""
    tarif: str = ""
    statut: str = Field("", description="Membership status of the member's season purchase (« Terminé »…)")
    saison: str = ""
    creneau_groupe: str = ""
    sex: Optional[Sex] = None


class GroupLoaded(BaseModel):
    """Members of the competition group added to a competition (load-group)."""
    added: int
    competition: Competition


class Done(BaseModel):
    """A write with nothing else to return."""
    status: Literal["success"]


class PastArchived(BaseModel):
    status: Literal["success"]
    archived: List[int] = Field(description="Ids of the competitions archived")


class Coach(BaseModel):
    id: int
    nom: str = ""


class HelloAssoItem(BaseModel):
    """An item of the HelloAsso mirror (`helloasso_items`) with the coach's link or ignore decision."""
    model_config = ConfigDict(extra="allow")

    id_item: int
    order_id: Optional[Union[int, str]] = None
    payer_nom: str = ""
    payer_prenom: str = ""
    montant: float = 0.0
    etat: str = ""
    date_item: str = ""
    licence_saisie: str = ""
    competition_saisie: str = ""
    campagne_slug: str = ""
    raw_json: str = Field("", description="HelloAsso's item as received (JSON text)")
    synced_at: Optional[str] = None
    competition_id: Optional[int] = None
    adherent_id: Optional[int] = None
    source: Optional[str] = Field(None, description="auto or manuel once linked")
    commentaire: str = ""
    ignore: bool = False
    ignore_motif: str = ""
    ignored_by: Optional[str] = None
    ignored_at: Optional[str] = None


class ItemLinked(BaseModel):
    status: Literal["success"]
    linked: bool = Field(description="The item now pays for a participant")


class ResultsFetched(BaseModel):
    """MyCompet results matched to the participants (the competition is updated: reload it)."""
    status: Literal["success"]
    url: str
    total_scraped: int
    matched_count: int
