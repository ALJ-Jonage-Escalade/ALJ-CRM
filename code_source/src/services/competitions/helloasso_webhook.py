"""
Service de réception et traitement des Webhooks HelloAsso (Paiements et Commandes).

Permet de :
1. Parser les notifications transmises par HelloAsso (événement Payment ou Order).
2. Extraire les articles vendus (items), leurs montants et champs personnalisés
   (licence FFME, numéro d'épreuve / compétition concernée).
3. Rapprocher automatiquement chaque article avec une compétition et un participant
   (via `domain.competitions.matching`).
4. Mettre à jour immédiatement la base de données (marquage « payé », montant réglé,
   sauvegarde de l'article dans le miroir HelloAsso).

Sécurité (le contenu d'une notification n'est jamais cru sur parole) :
- Jeton secret : si HELLOASSO_WEBHOOK_TOKEN est défini, l'URL déclarée chez
  HelloAsso doit être « /webhooks/helloasso?token=<secret> » ; toute requête
  sans le bon jeton est refusée (401).
- Re-vérification : si les identifiants API HelloAsso sont disponibles, seuls les
  identifiants d'articles sont lus dans la notification ; montant, état, payeur et
  champs personnalisés sont relus depuis l'API HelloAsso officielle.
- En production (contrôle d'accès actif), une notification n'est traitée que si
  l'une au moins de ces deux vérifications est possible (fail-closed).
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from domain.competitions.matching import auto_link_items, summarize_items
from domain.helloasso_campaigns import parse_campaign_identifier
from domain.competitions.models import PAIEMENT_PAYE
from domain.errors import Forbidden, UpstreamUnavailable
from infrastructure.firestore.app_settings import HELLOASSO_COMPETITION_CAMPAIGN, AppSettingsRepository
from infrastructure.firestore.competitions import competitions, helloasso_items, member_directory, participants
from infrastructure.helloasso import api as helloasso_api
from infrastructure.security.api_auth import auth_enforced, constant_time_equals
from infrastructure.security.secret_store import SecretStore
from services.competitions.all_paid_notification import check_and_notify_all_paid
from services.competitions.store import drops_cache

logger = logging.getLogger("alj")

Tuple_Items = Tuple[str, List[Dict[str, Any]]]

# Nombre maximal d'articles relus par notification (garde-fou anti-abus)
MAX_VERIFIED_ITEMS = 50


class HelloAssoWebhookService:
    """Service de gestion des webhooks HelloAsso."""

    @classmethod
    def extract_items_from_payload(cls, payload: Dict[str, Any]) -> Tuple_Items:
        """
        Extrait les articles normalisés à partir de tout type de payload HelloAsso
        (événement 'Payment', 'Order', 'Form', ou liste brute d'articles).
        """
        event_type = payload.get("eventType") or "Unknown"
        data = cls._event_data(payload)

        items: List[Dict[str, Any]] = []

        # 1. Si le payload contient directement une liste d'items
        if isinstance(data.get("items"), list) and data.get("items"):
            items = data["items"]
        # 2. Si le payload est lui-même un item individuel (contient un id et un montant)
        elif data.get("id") and (data.get("amount") is not None or data.get("price") is not None):
            items = [data]
        # 3. Événement 'Payment' contenant des paiements mais pas directement de liste items
        elif event_type == "Payment" or data.get("paymentMeans"):
            payer = data.get("payer") or {}
            user = {
                "firstName": payer.get("firstName") or data.get("payer_firstName") or "",
                "lastName": payer.get("lastName") or data.get("payer_lastName") or ""
            }
            order = data.get("order") or {}
            custom_fields = data.get("customFields") or []

            items = [{
                "id": data.get("id"),
                "amount": data.get("amount") or 0,
                "state": data.get("state") or "Processed",
                "date": data.get("date") or datetime.datetime.now().isoformat(),
                "user": user,
                "order": order,
                "customFields": custom_fields
            }]

        return event_type, items

    # ------------------------------------------------------------------
    # Vérification de l'authenticité
    # ------------------------------------------------------------------
    @classmethod
    def check_token(cls, token: Optional[str]) -> Optional[bool]:
        """True/False si un jeton secret est configuré (correct ou non), None sinon."""
        expected = (SecretStore.get_secret("HELLOASSO_WEBHOOK_TOKEN") or "").strip()
        if not expected:
            return None
        return bool(token) and constant_time_equals((token or "").strip(), expected)

    @staticmethod
    def _event_data(payload: Dict[str, Any]) -> Dict[str, Any]:
        """The `data` object of a notification, or the payload itself when it has none."""
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    @staticmethod
    def _ids(objs: object) -> List[int]:
        """The integer `id` of each object of a JSON list; entries without a valid one are skipped."""
        ids = []
        for o in objs if isinstance(objs, list) else []:
            if not isinstance(o, dict) or o.get("id") is None:
                continue
            try:
                ids.append(int(o["id"]))
            except (TypeError, ValueError):
                continue
        return ids

    @classmethod
    def fetch_verified_items(cls, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Relit depuis l'API HelloAsso les articles visés par la notification.

        Seuls les identifiants (articles, commande, paiement) sont pris dans le
        payload ; un identifiant inconnu de HelloAsso est simplement ignoré.
        """
        event_type = payload.get("eventType") or ""
        data = cls._event_data(payload)
        try:
            item_ids = cls._ids(data.get("items"))
            if not item_ids and data.get("id") is not None:
                order_id = None
                if event_type == "Payment":
                    payment = helloasso_api.get_payment(data.get("id")) or {}
                    item_ids = cls._ids(payment.get("items"))
                    order_id = (payment.get("order") or {}).get("id")
                elif event_type == "Order":
                    order_id = data.get("id")
                if not item_ids and order_id is not None:
                    order = helloasso_api.get_order(order_id) or {}
                    item_ids = cls._ids(order.get("items"))

            items = []
            for item_id in list(dict.fromkeys(item_ids))[:MAX_VERIFIED_ITEMS]:
                item = helloasso_api.get_item(item_id)
                if item and item.get("id") is not None:
                    items.append(item)
                else:
                    logger.warning("[WEBHOOK_HELLOASSO] Article #%s inconnu de l'API HelloAsso : ignoré", item_id)
            return items
        except helloasso_api.HelloAssoApiError as e:
            # 503 : HelloAsso renverra la notification plus tard
            raise UpstreamUnavailable(f"Vérification auprès de HelloAsso impossible : {e}", "helloasso_unreachable") from e

    @classmethod
    @drops_cache  # writes competition documents outside the @write services
    def verify_and_reconcile_notification(cls, payload: Dict[str, Any], token: Optional[str] = None) -> Dict[str, Any]:
        """Point d'entrée sécurisé du webhook. Refusals: Forbidden (token missing or wrong), UpstreamUnavailable
        (the notification cannot be checked: HelloAsso unreachable, or neither token nor API credentials configured)."""
        token_ok = cls.check_token(token)
        if token_ok is False:
            raise Forbidden("Jeton de notification HelloAsso absent ou invalide", "bad_token")

        if helloasso_api.credentials_configured():
            items = cls.fetch_verified_items(payload)
            report = cls.reconcile_payment_items(payload, items=items)
            report["verified"] = "api"
            return report

        if token_ok or not auth_enforced():
            report = cls.reconcile_payment_items(payload)
            report["verified"] = "token" if token_ok else "none"
            return report

        raise UpstreamUnavailable(
            "Notification non vérifiable : configurez HELLOASSO_WEBHOOK_TOKEN "
            "ou les identifiants API HelloAsso sur le serveur.",
            "not_verifiable",
        )

    @staticmethod
    def item_form_slug(raw: Dict[str, Any]) -> str:
        return str((raw.get("order") or {}).get("formSlug") or raw.get("formSlug") or "").strip()

    @classmethod
    def competition_form_slug(cls) -> str:
        """Slug du formulaire HelloAsso des compétitions (réglage HELLOASSO_COMPETITION_CAMPAIGN), "" sans réglage.
        A settings read failure is raised: answered as "no setting", it would let every other HelloAsso sale
        into the payment mirror."""
        ref = AppSettingsRepository.get(HELLOASSO_COMPETITION_CAMPAIGN)
        if not isinstance(ref, str) or not ref.strip():
            return ""
        try:
            return parse_campaign_identifier(ref)["slug"]
        except ValueError:
            logger.warning("[WEBHOOK_HELLOASSO] Réglage %s inexploitable (%r) : aucun filtre de formulaire",
                           HELLOASSO_COMPETITION_CAMPAIGN, ref)
            return ""

    @classmethod
    def filter_competition_form(cls, raw_items: List[Dict[str, Any]]):
        """Sépare les articles du formulaire de compétition des autres.

        Retourne (articles_retenus, slugs_des_articles_écartés). Sans réglage, ou
        pour un article dont le formulaire est inconnu, rien n'est écarté.
        """
        expected = cls.competition_form_slug().lower()
        if not expected:
            return list(raw_items), []
        kept, others = [], []
        for raw in raw_items:
            slug = cls.item_form_slug(raw)
            if slug and slug.lower() != expected:
                others.append(slug)
            else:
                kept.append(raw)
        return kept, others


    # ------------------------------------------------------------------
    # Traitement
    # ------------------------------------------------------------------
    @classmethod
    def reconcile_payment_items(cls, payload: Dict[str, Any],
                        items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Traite une notification Webhook HelloAsso complète :
        - Extrait les articles.
        - Tente le rapprochement avec la compétition et le participant.
        - Met à jour le statut du participant en base si le match est établi.
        - Enregistre l'article dans le miroir HelloAsso pour l'audit.

        items : articles déjà vérifiés auprès de l'API HelloAsso (prioritaires sur
        le contenu du payload, qui ne sert alors qu'à connaître le type d'événement).
        """
        if items is None:
            event_type, raw_items = cls.extract_items_from_payload(payload)
        else:
            event_type, raw_items = (payload.get("eventType") or "Unknown"), list(items)

        # Seuls les articles du formulaire « compétitions » configuré sont traités :
        # les autres ventes HelloAsso de l'association (boutique, adhésions…) ne
        # doivent pas polluer le miroir des paiements de compétition.
        raw_items, other_forms = cls.filter_competition_form(raw_items)
        if other_forms:
            logger.info("[WEBHOOK_HELLOASSO] %d article(s) d'un autre formulaire ignoré(s) : %s",
                        len(other_forms), ", ".join(sorted({s or '?' for s in other_forms})))

        if not raw_items:
            return {
                "status": "ignored",
                "message": ("Articles hors formulaire de compétition : ignorés."
                            if other_forms else "Aucun article (item) exploitable dans ce payload."),
                "other_forms": sorted({s or "?" for s in other_forms}),
                "event_type": event_type,
                "processed_count": 0,
                "matches": [],
                "anomalies": []
            }

        summarized = summarize_items(raw_items)
        computed_links = auto_link_items(
            items=summarized,
            competitions=[c.to_dict() for c in competitions.list_competitions()],
            adherents=member_directory.list_members(),
            existing_links=helloasso_items.list_helloasso_links(),
        )
        # Items already received: HelloAsso redelivers notifications, which must not undo a coach's cancellation
        known_items = {str(item_id) for item_id in helloasso_items.known_helloasso_item_ids()}

        matches: List[Dict[str, Any]] = []
        anomalies: List[Dict[str, Any]] = []
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for raw, item_summary in zip(raw_items, summarized, strict=False):
            link = computed_links.get(item_summary.get("id_item")) or {}
            kind, record = cls._apply_item(raw, item_summary, link, known_items, now_str)
            (matches if kind == "match" else anomalies).append(record)

        # Si tous les compétiteurs ont finalisé leur paiement, expédition de la notification
        notified_competitions = []
        for competition_id in {m["competition_id"] for m in matches}:
            try:
                if check_and_notify_all_paid(competition_id):
                    notified_competitions.append(competition_id)
            except Exception:  # payments are recorded: a failed notice must not fail the notification
                logger.exception("[WEBHOOK_HELLOASSO] Notification « tous payés » impossible pour la compétition #%s",
                                 competition_id)

        return {
            "status": "success",
            "event_type": event_type,
            "processed_count": len(raw_items),
            "matched_count": len(matches),
            "anomalies_count": len(anomalies),
            "matches": matches,
            "anomalies": anomalies,
            "notified_competitions": notified_competitions,
            "timestamp": now_str
        }

    @classmethod
    def _apply_item(cls, raw: Dict[str, Any], item_summary: Dict[str, Any], link: Dict[str, Any],
                    known_items: Set[str], now_str: str) -> Tuple[Literal["match", "anomaly"], Dict[str, Any]]:
        """Mirrors one item, then records its payment on the participant the matching found.
        Returns ("match", details) or ("anomaly", details with the reason)."""
        item_id = item_summary.get("id_item")
        order_ref = item_summary.get("commande") or str((raw.get("order") or {}).get("id") or "")
        amount = float(item_summary.get("montant") or 0.0)
        payer_name = item_summary.get("payeur") or ""
        licence = item_summary.get("licence") or ""

        mirrored = False
        try:
            helloasso_items.update_helloasso_mirror(
                summarized=[item_summary], raw_items=[raw], campagne_slug=cls.item_form_slug(raw))
            mirrored = True
        except Exception:  # the payment is still recorded below, from this item's amount alone
            logger.exception("[WEBHOOK_HELLOASSO] Sauvegarde miroir de l'article #%s impossible", item_id)

        competition_id = link.get("competition_id")
        adherent_id = link.get("adherent_id")
        if not competition_id or item_id is None:  # an item without id gets no link from the matching
            return "anomaly", {
                "id_item": item_id,
                "payer": payer_name,
                "montant": amount,
                "licence_saisie": licence,
                "competition_saisie": item_summary.get("competition") or "",
                "reason": "Numéro ou nom de compétition non reconnu sur le formulaire HelloAsso"
            }
        if not adherent_id:
            return "anomaly", {
                "id_item": item_id,
                "payer": payer_name,
                "montant": amount,
                "competition_id": competition_id,
                "licence_saisie": licence,
                "reason": "Compétition reconnue mais aucun adhérent trouvé par licence ou nom"
            }

        helloasso_items.set_item_link(id_item=item_id, competition_id=competition_id, adherent_id=adherent_id,
                                            source="webhook")

        payment = _ItemPayment(competition_id, adherent_id, mirrored, amount, order_ref,
                               item_summary.get("date_item") or now_str)
        # Nothing written: the member is not listed yet, or the coach cancelled them. A new payment lists them
        # (selected and paid) and reactivates a cancellation; a redelivered notification of an item already
        # received only lists a member who is missing.
        if not _record_payment(payment):
            added = participants.add_participant_doc(
                competition_id=competition_id,
                adherent_id=adherent_id,
                selectionne=True,
                reactivate_cancelled=str(item_id) not in known_items,
            )
            if added is not None:
                _record_payment(payment)

        return "match", {
            "id_item": item_id,
            "competition_id": competition_id,
            "adherent_id": adherent_id,
            "payer": payer_name,
            "montant": amount,
            "order_ref": order_ref,
            "licence": licence,
            "status": PAIEMENT_PAYE,
        }


@dataclass(frozen=True)
class _ItemPayment:
    competition_id: int
    adherent_id: int
    mirrored: bool  # the item reached the HelloAsso mirror
    amount: float
    order_ref: str
    item_date: str


def _record_payment(payment: _ItemPayment) -> bool:
    """Participant's payment = sum of every paid item linked to them (a 2nd payment adds to the 1st).
    Item missing from the mirror (failed write): its own amount only. Returns whether a participant was updated."""
    if payment.mirrored:
        return helloasso_items.refresh_helloasso_payment(payment.competition_id, payment.adherent_id)
    return participants.apply_helloasso_payment(
        competition_id=payment.competition_id, adherent_id=payment.adherent_id, montant_paye=payment.amount,
        order_ref=payment.order_ref, date_synchro=payment.item_date)
