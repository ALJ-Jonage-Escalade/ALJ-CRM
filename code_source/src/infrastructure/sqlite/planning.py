"""Training slots (`planning` table) and their HelloAsso tarifs."""

from __future__ import annotations

import json
from typing import Optional

from domain.members.planning_groups import is_autonomous_type
from infrastructure.sqlite.connection import SqliteDatabase


def _json_list(raw: Optional[str]) -> list:
    """A list column stored as JSON; [] when empty or unreadable."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


class PlanningRepository:
    @classmethod
    def load_planning_data(cls) -> list:
        """Charge l'ensemble du planning de créneaux depuis SQLite."""
        with SqliteDatabase.connect() as conn:
            rows = conn.execute("SELECT * FROM planning ORDER BY id ASC").fetchall()
        planning_list = []
        for row in rows:
            row_dict = dict(row)
            row_dict["encadrants"] = _json_list(row_dict.get("encadrants"))
            row_dict["helloasso_tarifs"] = _json_list(row_dict.get("helloasso_tarifs"))  # HelloAsso tariffs of the slot
            row_dict["seance_autonome"] = bool(row_dict.get("seance_autonome"))
            planning_list.append(row_dict)
        return planning_list

    @classmethod
    def load_creneaux_groups(cls) -> list:
        """Agrège le planning par groupe de créneau unique (un groupe peut posséder
        plusieurs créneaux horaires et plusieurs tarifs HelloAsso).
        Retourne une liste de dicts {groupe, tarifs, slots, seance_autonome, type_autonome} triée par nom de groupe ;
        seance_autonome / type_autonome : vrai si l'un de ses créneaux est coché « Séance autonome » / de type Autonome."""
        creneaux: dict[str, dict] = {}
        order = []
        for item in cls.load_planning_data():
            g_name = str(item.get("groupe") or "").strip()
            if not g_name:
                continue
            if g_name not in creneaux:
                creneaux[g_name] = {"tarifs": [], "slots": [], "seance_autonome": False, "type_autonome": False}
                order.append(g_name)
            for t in item.get("helloasso_tarifs") or []:
                t_str = str(t).strip()
                if t_str and t_str not in creneaux[g_name]["tarifs"]:
                    creneaux[g_name]["tarifs"].append(t_str)
            creneaux[g_name]["seance_autonome"] |= bool(item.get("seance_autonome"))
            creneaux[g_name]["type_autonome"] |= is_autonomous_type(item.get("type"))
            creneaux[g_name]["slots"].append((
                str(item.get("jour") or "").strip(),
                str(item.get("horaires") or "").strip()
            ))
        return [
            {"groupe": g, **creneaux[g]}
            for g in sorted(order)
        ]

    @classmethod
    def save_planning_data(cls, planning_list: list):
        """Remplace le planning complet dans SQLite (répliqué vers Firestore comme toute écriture du cache)."""
        with SqliteDatabase.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM planning")
            for item in planning_list:
                enc_json = json.dumps(item.get("encadrants", []), ensure_ascii=False)
                tarifs_json = json.dumps(item.get("helloasso_tarifs", []), ensure_ascii=False)
                cursor.execute("""
                    INSERT OR REPLACE INTO planning (id, groupe, type, categorie_age, whatsapp_link, jour, horaires, encadrants, helloasso_tarifs, naissance_min, naissance_max, seance_autonome)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("id"),
                    item.get("groupe"),
                    item.get("type", "cours"),
                    item.get("categorie_age", ""),
                    item.get("whatsapp_link", ""),
                    item.get("jour", "Lundi"),
                    item.get("horaires", ""),
                    enc_json,
                    tarifs_json,
                    str(item.get("naissance_min") or ""),
                    str(item.get("naissance_max") or ""),
                    int(bool(item.get("seance_autonome")))
                ))

    @classmethod
    def save_planning_item(cls, item: dict) -> dict:
        """Crée ou met à jour un créneau unique dans la table planning."""
        with SqliteDatabase.transaction() as conn:
            cursor = conn.cursor()
            item_id = item.get("id")
            if not item_id or int(item_id) <= 0:
                cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM planning")
                item_id = cursor.fetchone()[0]
                item["id"] = item_id

            enc_json = json.dumps(item.get("encadrants", []), ensure_ascii=False)
            tarifs_json = json.dumps(item.get("helloasso_tarifs", []), ensure_ascii=False)

            cursor.execute("""
                INSERT OR REPLACE INTO planning (id, groupe, type, categorie_age, whatsapp_link, jour, horaires, encadrants, helloasso_tarifs, naissance_min, naissance_max, seance_autonome)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                int(item_id),
                str(item.get("groupe") or "").strip(),
                str(item.get("type") or "cours").strip(),
                str(item.get("categorie_age") or "").strip(),
                str(item.get("whatsapp_link") or "").strip(),
                str(item.get("jour") or "Lundi").strip(),
                str(item.get("horaires") or "").strip(),
                enc_json,
                tarifs_json,
                str(item.get("naissance_min") or "").strip(),
                str(item.get("naissance_max") or "").strip(),
                int(bool(item.get("seance_autonome")))
            ))
        return item

    @classmethod
    def delete_planning_item(cls, item_id: int) -> bool:
        """Supprime un créneau par son ID."""
        with SqliteDatabase.transaction() as conn:
            return conn.execute("DELETE FROM planning WHERE id = ?", (int(item_id),)).rowcount > 0
