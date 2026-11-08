"""HelloAsso mirror: `helloasso_items` documents with their embedded link to a participant,
and the payments those links carry over to the participants."""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

from domain.competitions import matching as competition_matching
from domain.competitions.models import (
    PAIEMENT_EN_ATTENTE,
    PAIEMENT_NON_INVITE,
    PAIEMENT_PAYE,
    PAIEMENT_STATUTS_ANNULES,
)
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.firestore.competitions.participants import MANUAL_PAYMENT_REF, ParticipantsMixin

logger = logging.getLogger("alj")


class ItemAlreadyLinked(Exception):
    """A HelloAsso item linked to a competition and a member cannot be ignored."""


class HelloAssoItemsMixin(ParticipantsMixin):
    """Mirror of the HelloAsso items, their links, and the payments applied from them."""

    # ------------------------------------------------------------------
    # Miroir HelloAsso (documents avec rattachement embarqué)
    # ------------------------------------------------------------------
    @staticmethod
    def _link_fields(competition_id, adherent_id, source, now: str) -> Dict[str, Any]:
        """Fields of an item's link to a participant (None everywhere: no link)."""
        return {"competition_id": competition_id, "adherent_id": adherent_id,
                "source": source, "link_updated_at": now}

    @staticmethod
    def _is_paid_item(item: Dict[str, Any]) -> bool:
        return str(item.get("etat") or "").lower() in {str(s).lower() for s in competition_matching.STATUTS_PAYES}

    @classmethod
    def _items_map(cls) -> Dict[int, Dict[str, Any]]:
        """{id_item: document miroir} — une seule lecture de la collection."""
        items = {}
        for d in FirestoreClient.list_documents(cls.COLLECTION_ITEMS):
            try:
                iid = int(d.get("id_item"))
            except (TypeError, ValueError):
                continue
            items[iid] = d
        return items

    @classmethod
    def known_helloasso_item_ids(cls) -> Set[int]:
        """Identifiers of the HelloAsso items already in the mirror."""
        return set(cls._items_map())

    @classmethod
    def update_helloasso_mirror(cls, summarized: list, raw_items: list,
                              campagne_slug: str) -> int:
        """Upsert du miroir : ce que dit HelloAsso remplace la copie, en préservant
        le commentaire et le rattachement (liens) de chaque article."""
        existing = cls._items_map()
        now = cls._now_display()
        writes = []
        written = 0
        # Champs appartenant à HelloAsso : pour un article déjà connu, seuls eux
        # sont réécrits (masque), afin de ne jamais écraser un rattachement, un
        # commentaire ou un « ignorer » saisi entre-temps depuis la PWA.
        helloasso_fields = ["id_item", "order_id", "payer_nom", "payer_prenom", "montant",
                            "etat", "date_item", "licence_saisie", "competition_saisie",
                            "campagne_slug", "raw_json", "synced_at"]
        for s, raw in zip(summarized or [], raw_items or [], strict=False):
            id_item = s.get("id_item")
            if id_item is None:
                continue
            payeur = str(s.get("payeur") or "")
            nom, _, prenom = payeur.partition(" ")
            doc = dict(existing.get(int(id_item)) or {})
            doc.update({
                "id_item": int(id_item),
                "order_id": s.get("commande") or None,
                "payer_nom": nom.strip(),
                "payer_prenom": prenom.strip(),
                "montant": float(s.get("montant") or 0.0),
                "etat": str(s.get("etat") or ""),
                "date_item": str(s.get("date_item") or ""),
                "licence_saisie": str(s.get("licence") or ""),
                "competition_saisie": str(s.get("competition") or ""),
                "campagne_slug": str(campagne_slug or ""),
                "raw_json": json.dumps(raw, ensure_ascii=False, default=str),
                "synced_at": now,
            })
            doc.setdefault("competition_id", None)
            doc.setdefault("adherent_id", None)
            doc.setdefault("source", None)
            doc.setdefault("link_updated_at", None)
            doc.setdefault("commentaire", "")
            write = {"path": f"{cls.COLLECTION_ITEMS}/{int(id_item)}", "data": doc}
            if int(id_item) in existing:
                write["data"] = {k: doc[k] for k in helloasso_fields}
                write["update_fields"] = helloasso_fields
            writes.append(write)
            written += 1
        if writes:
            FirestoreClient.batch_upsert(writes)
        return written

    @classmethod
    def list_helloasso_links(cls) -> dict:
        result = {}
        for iid, doc in cls._items_map().items():
            source = doc.get("source")
            comp_id = doc.get("competition_id")
            adh_id = doc.get("adherent_id")
            if doc.get("ignore") is True and (comp_id is None or adh_id is None):
                source = "ignore"
            if source or comp_id is not None or adh_id is not None:
                result[iid] = {
                    "competition_id": comp_id,
                    "adherent_id": adh_id,
                    "source": source or "",
                }
        return result

    @classmethod
    def set_item_link(cls, id_item: int, competition_id, adherent_id,
                      source: str = "manuel") -> bool:
        FirestoreClient.update_fields(cls.COLLECTION_ITEMS, str(id_item),
                                      cls._link_fields(competition_id, adherent_id, source,
                                                       cls._now_iso()))
        return True

    @classmethod
    def save_manual_link(cls, id_item: int, competition_id: Optional[int],
                         adherent_id: Optional[int], commentaire: str = "") -> bool:
        """Link chosen by a coach (one write). A partial choice (competition or member only)
        is stored without a source; choosing both marks the link `manuel`, which the
        automatic matching never overwrites. Also lifts an `ignore` flag."""
        linked = competition_id is not None and adherent_id is not None
        now = cls._now_iso()
        patch = cls._link_fields(competition_id, adherent_id, "manuel" if linked else None, now)
        patch.update({"commentaire": str(commentaire or ""), "ignore": False, "updated_at": now})
        FirestoreClient.update_fields(cls.COLLECTION_ITEMS, str(id_item), patch)
        return True

    @classmethod
    def set_item_ignored(cls, id_item: int, ignore: bool, motif: str = "",
                         commentaire: str = "", by: str = "") -> bool:
        """Ignores (test, purchase unrelated to a competition…) or restores a HelloAsso item.

        Written with a precondition on the version read: an item linked meanwhile (webhook,
        another coach) raises ItemAlreadyLinked instead of being ignored. Returns False when
        the item does not exist."""
        def attempt():
            doc = FirestoreClient.get_document(cls.COLLECTION_ITEMS, str(id_item))
            if doc is None:
                return False
            now = cls._now_iso()
            if ignore:
                if doc.get("competition_id") is not None and doc.get("adherent_id") is not None:
                    raise ItemAlreadyLinked(id_item)
                patch = cls._link_fields(None, None, None, now)
                patch.update({"ignore": True, "ignore_motif": str(motif or ""),
                              "commentaire": str(commentaire or motif or ""),
                              "ignored_at": now, "ignored_by": str(by or ""), "updated_at": now})
            else:
                patch = {"ignore": False, "ignore_motif": "", "ignored_at": None,
                         "ignored_by": None, "commentaire": str(commentaire or ""),
                         "updated_at": now}
            FirestoreClient.update_fields(cls.COLLECTION_ITEMS, str(id_item), patch,
                                          expected_update_time=doc.get("_update_time"))
            return True
        return bool(cls._with_retries(f"Article HelloAsso #{id_item}", attempt))

    @classmethod
    def list_item_docs(cls) -> List[Dict[str, Any]]:
        """HelloAsso mirror documents as stored (links, comments and ignore flags included),
        most recent first: the shape the web pages use."""
        docs = [cls._clean_doc(d) for d in cls._items_map().values()]
        docs.sort(key=lambda d: (str(d.get("date_item") or ""), int(d.get("id_item") or 0)),
                  reverse=True)
        return docs

    @classmethod
    def clear_item_link(cls, id_item: int) -> bool:
        """Efface le rattachement d'un article (choix « Ignorer »)."""
        try:
            FirestoreClient.update_fields(cls.COLLECTION_ITEMS, str(id_item),
                                          cls._link_fields(None, None, None, cls._now_iso()))
            return True
        except FirestoreError:
            return False

    @classmethod
    def replace_auto_links(cls, links: dict) -> int:
        """Remplace tous les liens 'auto' par le calcul courant ; les liens
        'manuel' sont intacts. `links` : retour de auto_link_items()."""
        items = cls._items_map()
        now = cls._now_display()
        writes = []
        for iid, doc in items.items():
            source = doc.get("source")
            if str(source or "") == "manuel" or doc.get("ignore") is True:
                continue
            link = (links or {}).get(iid)
            fields = (cls._link_fields(link.get("competition_id"), link.get("adherent_id"), "auto", now)
                      if link is not None else cls._link_fields(None, None, None, now))
            if any(doc.get(k) != v for k, v in fields.items()):
                writes.append({"path": f"{cls.COLLECTION_ITEMS}/{iid}",
                               "data": fields, "update_fields": list(fields)})
        if writes:
            FirestoreClient.batch_upsert(writes)
        return len(writes)

    @classmethod
    def get_item(cls, id_item: int) -> Optional[Dict[str, Any]]:
        return FirestoreClient.get_document(cls.COLLECTION_ITEMS, str(id_item))

    @classmethod
    def save_item_comment(cls, id_item: int, comment: str) -> bool:
        FirestoreClient.update_fields(cls.COLLECTION_ITEMS, str(id_item),
                                      {"commentaire": str(comment or "")})
        return True

    @classmethod
    def _participant_amount(cls, comp_doc: Optional[Dict[str, Any]], adherent_id) -> Optional[float]:
        for p in (comp_doc or {}).get("participants") or []:
            if p.get("adherent_id") == adherent_id:
                return float(p.get("montant_paye") or 0.0)
        return None

    @classmethod
    def list_mirror_items(cls) -> list:
        items = cls._items_map()
        comps = {}
        for d in cls._list_comp_docs():
            comps[d.get("id")] = d
        adh = cls._adherent_map()
        rows = []
        for iid, doc in items.items():
            comp_id = doc.get("competition_id")
            adh_id = doc.get("adherent_id")
            comp_doc = comps.get(comp_id) if comp_id is not None else None
            a_doc = adh.get(adh_id) or {}
            rows.append({
                "id_item": iid,
                "order_id": doc.get("order_id"),
                "payer_nom": doc.get("payer_nom") or "",
                "payer_prenom": doc.get("payer_prenom") or "",
                "montant": float(doc.get("montant") or 0.0),
                "etat": str(doc.get("etat") or ""),
                "date_item": str(doc.get("date_item") or ""),
                "licence_saisie": str(doc.get("licence_saisie") or ""),
                "competition_saisie": str(doc.get("competition_saisie") or ""),
                "campagne_slug": str(doc.get("campagne_slug") or ""),
                "raw_json": str(doc.get("raw_json") or ""),
                "synced_at": str(doc.get("synced_at") or ""),
                "commentaire": str(doc.get("commentaire") or ""),
                "ignore": doc.get("ignore") is True,
                "ignore_motif": str(doc.get("ignore_motif") or ""),
                "competition_id": comp_id,
                "adherent_id": adh_id,
                "source": doc.get("source"),
                "competition_nom": (comp_doc or {}).get("nom") or "",
                "adherent_nom": (a_doc.get("nom") or ""),
                "adherent_prenom": (a_doc.get("prenom") or ""),
                "participant_montant_paye": cls._participant_amount(comp_doc, adh_id)
                if comp_id is not None and adh_id is not None else None,
            })
        rows.sort(key=lambda r: (r["date_item"], r["id_item"]), reverse=True)
        return rows

    @classmethod
    def list_unlinked_items(cls) -> list:
        adh = {a["id"]: a for a in cls.list_members()}
        result = []
        for it in cls.list_mirror_items():
            if not cls._is_paid_item(it):
                continue
            if it.get("competition_id") is not None and it.get("adherent_id") is not None:
                continue
            if it.get("ignore") is True:
                continue
            lic = re.sub(r"\D", "", str(it.get("licence_saisie") or ""))
            preselect = it.get("adherent_id")
            if preselect is None and lic:
                preselect = next((aid for aid, a in adh.items()
                                  if re.sub(r"\D", "", str(a.get("num_licence") or "")) == lic), None)
            comp_name_val, comp_num_val = "", ""
            raw_json_str = it.get("raw_json")
            if raw_json_str:
                try:
                    raw_data = json.loads(raw_json_str)
                    comp_name_val = competition_matching.extract_competition_name(raw_data)
                    comp_num_val = competition_matching.extract_competition_number(raw_data, fallback=False)
                except Exception:
                    logger.warning("raw_json HelloAsso illisible pour l'item %s", it.get("id_item"), exc_info=True)
            result.append({
                "id_item": it["id_item"],
                "payer": f"{it.get('payer_nom') or ''} {it.get('payer_prenom') or ''}".strip() or "Inconnu",
                "montant": float(it.get("montant") or 0.0),
                "etat": str(it.get("etat") or ""),
                "date_item": str(it.get("date_item") or ""),
                "order_ref": str(it.get("order_id") or ""),
                "licence": str(it.get("licence_saisie") or ""),
                "valeur_champ": str(it.get("competition_saisie") or ""),
                "competition_concernee": comp_name_val,
                "numero_competition": comp_num_val,
                "adherent_id": preselect,
                "participant": "",
                "commentaire": str(it.get("commentaire") or ""),
            })
        result.sort(key=lambda r: (str(r.get("payer") or "").lower(), r.get("id_item") or 0))
        return result

    @classmethod
    def apply_links_to_participants(cls) -> int:
        """Reporte les liens valides sur les participants (groupé par épreuve :
        une lecture + une écriture Firestore par compétition concernée)."""
        groupes: Dict[tuple, Dict[str, Any]] = {}
        for it in cls._items_map().values():
            if not cls._is_paid_item(it):
                continue
            comp_id = it.get("competition_id")
            adherent_id = it.get("adherent_id")
            if comp_id is None or adherent_id is None:
                continue
            g = groupes.setdefault((comp_id, adherent_id),
                                   {"montant": 0.0, "orders": []})
            g["montant"] += float(it.get("montant") or 0.0)
            order = str(it.get("order_id") or "")
            if order:
                g["orders"].append(order)

        by_comp: Dict[int, List[tuple]] = {}
        for (comp_id, adherent_id) in groupes:
            by_comp.setdefault(comp_id, []).append(adherent_id)

        now = cls._now_display()
        applied = 0
        for comp_id, adherent_ids in by_comp.items():
            done = {"count": 0}

            def mutate(parts, comp_id=comp_id, adherent_ids=adherent_ids, done=done):
                done["count"] = 0
                index = {p.get("adherent_id"): p for p in parts}
                for adherent_id in adherent_ids:
                    g = groupes[(comp_id, adherent_id)]
                    p = index.get(adherent_id)
                    if p is None:
                        p = cls._new_participant(adherent_id, True)
                        parts.append(p)
                        index[adherent_id] = p
                    elif (p.get("statut_paiement") or "") in PAIEMENT_STATUTS_ANNULES:
                        continue
                    else:
                        p["selectionne"] = True
                    p["statut_paiement"] = PAIEMENT_PAYE
                    p["montant_paye"] = round(g["montant"], 2)
                    p["commande_helloasso"] = ", ".join(g["orders"])
                    p["updated_at"] = now
                    done["count"] += 1
                return parts
            if cls._mutate_participants(comp_id, mutate) is not None:
                applied += done["count"]
        return applied

    @classmethod
    def refresh_helloasso_payment(cls, competition_id: int, adherent_id: int) -> bool:
        """Recomputes a participant's HelloAsso payment from the paid items linked to them
        (rule of apply_links_to_participants): sum of their amounts, their orders. With none
        left (item linked elsewhere or not paid), a payment that came from HelloAsso is undone:
        back to waiting for payment (or not invited when unselected). Cancellations and manual
        payments are kept. Returns whether the participant row was written."""
        linked = [it for it in cls._items_map().values()
                  if it.get("competition_id") == competition_id and it.get("adherent_id") == adherent_id
                  and cls._is_paid_item(it)]
        montant = round(sum(float(it.get("montant") or 0.0) for it in linked), 2)
        orders = ", ".join(str(it["order_id"]) for it in linked if it.get("order_id"))

        def change(participant):
            statut = participant.get("statut_paiement") or ""
            if statut in PAIEMENT_STATUTS_ANNULES:
                return False  # the coach's cancellation is never overwritten
            if linked:
                participant.update(statut_paiement=PAIEMENT_PAYE, montant_paye=montant, commande_helloasso=orders)
                return None
            if statut != PAIEMENT_PAYE or (participant.get("commande_helloasso") or "") in ("", MANUAL_PAYMENT_REF):
                return False
            participant.update(statut_paiement=PAIEMENT_EN_ATTENTE if participant.get("selectionne") else PAIEMENT_NON_INVITE,
                     montant_paye=0.0, commande_helloasso="")
            return None
        return cls._update_participant(competition_id, adherent_id, change) is not None
