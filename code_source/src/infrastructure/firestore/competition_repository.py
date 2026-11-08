"""
Référentiel des compétitions sur Google Cloud Firestore (source de vérité unique).

Remplace l'ancienne base SQLite locale (database_Competition.db) : l'API (lue et
écrite par l'application Vue, frontend/) s'appuie sur ce modèle de documents
Firestore :

- `competitions/{id}`        : épreuve + tableau `participants` embarqué ;
- `coaches/{id}`             : référentiel des coachs ;
- `adherents/{id}`           : instantané des adhérents (miroir de database.db) ;
- `helloasso_items/{id_item}` : miroir des paiements HelloAsso + rattachements.

The only competition store left (the SQLite one was removed). All methods are classmethods.

Normalisation des identifiants : les documents hérités créés par la page web
avaient un identifiant Firestore aléatoire. À la première lecture d'une épreuve,
le document est recopié vers l'identifiant canonique `str(id)` et le document
hérité est supprimé ; les écritures ciblent toujours l'identifiant canonique.
"""
from infrastructure.firestore.competitions.coaches import CoachesMixin
from infrastructure.firestore.competitions.competitions import CompetitionsMixin
from infrastructure.firestore.competitions.helloasso_items import HelloAssoItemsMixin, ItemAlreadyLinked
from infrastructure.firestore.competitions.participants import (
    DEFAULT_STATUT_NOUVEAU_PARTICIPANT,
    MANUAL_PAYMENT_REF,
    ParticipantAlreadyPaid,
    ParticipantChanged,
    RowGuard,
    unchanged_since_guard,
)

__all__ = [
    "CompetitionRepository",
    "DEFAULT_STATUT_NOUVEAU_PARTICIPANT",
    "ItemAlreadyLinked",
    "MANUAL_PAYMENT_REF",
    "ParticipantAlreadyPaid",
    "ParticipantChanged",
    "RowGuard",
    "unchanged_since_guard",
]


class CompetitionRepository(CompetitionsMixin, HelloAssoItemsMixin, CoachesMixin):
    """CRUD des épreuves / participants / coachs / miroir HelloAsso sur Firestore.

    One class over the mixins of infrastructure.firestore.competitions (one per domain):
    callers and tests keep using and patching this class only."""
