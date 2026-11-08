"""Training slots (`planning` table) and their HelloAsso tarifs."""

from __future__ import annotations

import json

from infrastructure.sqlite.connection import SqliteDatabase


class PlanningRepository:
    @classmethod
    def load_planning_data(cls) -> list:
        """Charge l'ensemble du planning de créneaux depuis SQLite."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM planning ORDER BY id ASC")
            rows = cursor.fetchall()
            planning_list = []
            for row in rows:
                row_dict = dict(row)
                
                # Désérialiser les encadrants
                encadrants_raw = row_dict.get("encadrants", "[]")
                if encadrants_raw:
                    try:
                        encadrants = json.loads(encadrants_raw)
                    except Exception:
                        encadrants = []
                else:
                    encadrants = []
                row_dict["encadrants"] = encadrants
                
                # Désérialiser les tarifs HelloAsso mappés
                tarifs_raw = row_dict.get("helloasso_tarifs", "[]")
                if tarifs_raw:
                    try:
                        tarifs = json.loads(tarifs_raw)
                    except Exception:
                        tarifs = []
                else:
                    tarifs = []
                row_dict["helloasso_tarifs"] = tarifs
                
                planning_list.append(row_dict)

            return planning_list
        except Exception as e:
            print(f"❌ [SQLITE] Erreur lors du chargement du planning : {e}")
            return []
        finally:
            conn.close()

    @classmethod
    def load_creneaux_groups(cls) -> list:
        """Agrège le planning par groupe de créneau unique (un groupe peut posséder
        plusieurs créneaux horaires et plusieurs tarifs HelloAsso).
        Retourne une liste de dicts {groupe, tarifs, slots} triée par nom de groupe."""
        creneaux = {}
        order = []
        for item in cls.load_planning_data():
            g_name = str(item.get("groupe") or "").strip()
            if not g_name:
                continue
            if g_name not in creneaux:
                creneaux[g_name] = {"tarifs": [], "slots": []}
                order.append(g_name)
            for t in item.get("helloasso_tarifs") or []:
                t_str = str(t).strip()
                if t_str and t_str not in creneaux[g_name]["tarifs"]:
                    creneaux[g_name]["tarifs"].append(t_str)
            creneaux[g_name]["slots"].append((
                str(item.get("jour") or "").strip(),
                str(item.get("horaires") or "").strip()
            ))
        return [
            {"groupe": g, "tarifs": creneaux[g]["tarifs"], "slots": creneaux[g]["slots"]}
            for g in sorted(order)
        ]

    @classmethod
    def save_planning_data(cls, planning_list: list):
        """Remplace le planning complet dans SQLite (répliqué vers Firestore comme toute écriture du cache)."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM planning")
            for item in planning_list:
                enc_json = json.dumps(item.get("encadrants", []), ensure_ascii=False)
                tarifs_json = json.dumps(item.get("helloasso_tarifs", []), ensure_ascii=False)
                cursor.execute("""
                    INSERT OR REPLACE INTO planning (id, groupe, type, categorie_age, whatsapp_link, jour, horaires, encadrants, helloasso_tarifs, naissance_min, naissance_max)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    str(item.get("naissance_max") or "")
                ))
            conn.commit()
            print("💾 [SQLITE] Planning enregistré avec succès dans SQLite.")
        except Exception as e:
            print(f"❌ [SQLITE] Erreur lors de la sauvegarde du planning : {e}")
            conn.rollback()
            raise e
        finally:
            conn.close()

    @classmethod
    def save_planning_item(cls, item: dict) -> dict:
        """Crée ou met à jour un créneau unique dans la table planning."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            item_id = item.get("id")
            if not item_id or int(item_id) <= 0:
                cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM planning")
                item_id = cursor.fetchone()[0]
                item["id"] = item_id

            enc_json = json.dumps(item.get("encadrants", []), ensure_ascii=False)
            tarifs_json = json.dumps(item.get("helloasso_tarifs", []), ensure_ascii=False)

            cursor.execute("""
                INSERT OR REPLACE INTO planning (id, groupe, type, categorie_age, whatsapp_link, jour, horaires, encadrants, helloasso_tarifs, naissance_min, naissance_max)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                str(item.get("naissance_max") or "").strip()
            ))
            conn.commit()
            print(f"💾 [SQLITE] Créneau #{item_id} ({item.get('groupe')}) enregistré avec succès.")
            return item
        except Exception as e:
            print(f"❌ [SQLITE] Erreur lors de l'enregistrement du créneau : {e}")
            conn.rollback()
            raise e
        finally:
            conn.close()

    @classmethod
    def delete_planning_item(cls, item_id: int) -> bool:
        """Supprime un créneau par son ID."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM planning WHERE id = ?", (int(item_id),))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                print(f"🗑️ [SQLITE] Créneau #{item_id} supprimé avec succès.")
            return deleted
        except Exception as e:
            print(f"❌ [SQLITE] Erreur lors de la suppression du créneau #{item_id} : {e}")
            conn.rollback()
            raise e
        finally:
            conn.close()
