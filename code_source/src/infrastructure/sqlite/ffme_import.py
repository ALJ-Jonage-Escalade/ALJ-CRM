"""FFME licensee and autonomy (badge rouge) imports from the federation Excel exports."""

from __future__ import annotations

import datetime
import os

from infrastructure.sqlite import schema_v2
from infrastructure.sqlite.connection import SqliteDatabase


class FfmeImportRepository:
    @classmethod
    def prepare_ffme_licensees(cls, excel_path: str) -> dict:
        """
        Phase A de l'import FFME — lit le fichier Excel, charge les utilisateurs et
        applique le rapprochement automatique (N° de licence puis Nom/Prénom).
        Ne modifie PAS la base. Retourne :
          {
            "updates":   [(match_type, licence, passeports, diplomas, document_sante, user_id), ...],
            "unmatched": [{"nom", "prenom", "licence", "birth_date", "passeports", "diplomes",
                           "document_sante"}, ...],
            "users":     [{"id", "last_name", "first_name", "licence_ffme", "birth_date"}, ...],
            "stats":     {"total_processed", "matched_by_licence", "matched_by_name", "errors"},
          }
        """
        import pandas as pd
        from domain.utils import normalize_name

        prep = {"updates": [], "unmatched": [], "users": [],
                "stats": {"total_processed": 0, "matched_by_licence": 0,
                          "matched_by_name": 0, "errors": []}}
        stats = prep["stats"]

        if not os.path.exists(excel_path):
            stats["errors"].append(f"Fichier introuvable : {excel_path}")
            return prep
        try:
            df = pd.read_excel(excel_path)
            required_cols = ["Nom", "Pr\u00e9nom", "N\u00b0 de licence"]
            if not all(col in df.columns for col in required_cols):
                try:
                    df_h1 = pd.read_excel(excel_path, header=1)
                    if all(col in df_h1.columns for col in required_cols):
                        df = df_h1
                except Exception:
                    pass
        except Exception as e:
            stats["errors"].append(f"Erreur de lecture Excel : {e}")
            return prep

        required_cols = ["Nom", "Pr\u00e9nom", "N\u00b0 de licence"]
        for col in required_cols:
            if col not in df.columns:
                stats["errors"].append(f"Colonne requise manquante dans le fichier Excel : {col}")
                return prep

        def _clean_licence(val):
            """Extrait le N° de licence numérique : retire l'enrobage formule Excel
            ('=\"636947\"'), le suffixe float ('636947.0') et tout caractère non numérique.
            La mise à jour du N° de licence utilise cette valeur nettoyée (cohérente avec
            l'index users_by_licence)."""
            s = str(val or "").strip()
            if s.endswith(".0"):
                s = s[:-2]
            return "".join(c for c in s if c.isdigit())

        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            cursor = conn.cursor()

            # Secours lecture des N° de licence : les exports FFME récents stockent la
            # colonne « N° de licence » en formule Excel ('=\"636947\"') SANS valeur
            # cachée — pandas la lit alors comme NaN. openpyxl (data_only=False) permet
            # de relire le texte de la formule et d'en extraire le numéro.
            openpyxl_licences = {}
            try:
                import openpyxl as _openpyxl
                _wb = _openpyxl.load_workbook(excel_path, read_only=True, data_only=False)
                _ws = _wb.active
                _rows = list(_ws.iter_rows(values_only=True))
                _wb.close()
                if _rows:
                    _headers = [str(h or "").strip() for h in _rows[0]]
                    if "N\u00b0 de licence" in _headers:
                        _ci = _headers.index("N\u00b0 de licence")
                        for _r in _rows[1:]:
                            _nom = str(_r[0] or "").strip() if len(_r) > 0 else ""
                            _prenom = str(_r[1] or "").strip() if len(_r) > 1 else ""
                            _val = _r[_ci] if _ci < len(_r) else None
                            openpyxl_licences[(_nom, _prenom)] = "" if _val is None else str(_val)
            except Exception:
                openpyxl_licences = {}

            cursor.execute("""
                SELECT id, last_name, first_name, licence_ffme,
                       COALESCE(birth_date, birth_date_raw, '') AS birth_date
                FROM users
            """)
            users = [dict(row) for row in cursor.fetchall()]
            prep["users"] = [
                {"id": u["id"], "last_name": u["last_name"], "first_name": u["first_name"],
                 "licence_ffme": u["licence_ffme"], "birth_date": u["birth_date"]}
                for u in users
            ]

            users_by_licence = {}
            users_by_name = {}
            for u in users:
                clean_lic = _clean_licence(u["licence_ffme"])
                if clean_lic:
                    users_by_licence[clean_lic] = u
                nk = normalize_name(u["last_name"])
                fk = normalize_name(u["first_name"])
                if nk and fk:
                    users_by_name[(nk, fk)] = u

            def _cell_str(row, key):
                val = row.get(key)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    return ""
                return str(val).strip() if not hasattr(val, "strftime") else val.strftime("%d/%m/%Y")

            has_sante_col = "Document de sant\u00e9" in df.columns

            for idx, row in df.iterrows():
                stats["total_processed"] += 1
                nom = str(row["Nom"] or "").strip()
                prenom = str(row["Pr\u00e9nom"] or "").strip()
                raw_lic = row["N\u00b0 de licence"]
                lic_str = "" if pd.isna(raw_lic) else _clean_licence(raw_lic)
                if not lic_str:
                    # Secours openpyxl : formules '=\"636947\"' sans valeur cachée
                    lic_str = _clean_licence(openpyxl_licences.get((nom, prenom), ""))

                matched = None
                if lic_str and lic_str in users_by_licence:
                    matched = users_by_licence[lic_str]
                    match_type = "licence"
                if not matched and nom and prenom:
                    key = (normalize_name(nom), normalize_name(prenom))
                    if key in users_by_name:
                        matched = users_by_name[key]
                        match_type = "name"
                if matched:
                    # Le N° de licence du fichier FFME (nettoyé) fait foi ; on conserve
                    # la licence existante uniquement si le fichier n'en fournit pas.
                    final_lic = lic_str if lic_str else _clean_licence(matched["licence_ffme"])
                    passports_str = _cell_str(row, "Passeports")
                    if passports_str.lower() in ("nan", "none", ""):
                        passports_str = ""
                    diplomas_str = _cell_str(row, "Dipl\u00f4mes")
                    if diplomas_str.lower() in ("nan", "none", ""):
                        diplomas_str = ""
                    sante_str = _cell_str(row, "Document de sant\u00e9") if has_sante_col else ""
                    if sante_str.lower() in ("nan", "none"):
                        sante_str = ""
                    prep["updates"].append(("Terminé", final_lic, passports_str, diplomas_str, sante_str, matched["id"]))
                    if match_type == "licence":
                        stats["matched_by_licence"] += 1
                    else:
                        stats["matched_by_name"] += 1
                else:
                    prep["unmatched"].append({
                        "nom": nom, "prenom": prenom, "licence": lic_str,
                        "birth_date": _cell_str(row, "Date de naissance"),
                        "passeports": _cell_str(row, "Passeports"),
                        "diplomes": _cell_str(row, "Dipl\u00f4mes"),
                        "document_sante": _cell_str(row, "Document de sant\u00e9") if has_sante_col else "",
                    })
        except Exception as e:
            stats["errors"].append(f"Erreur lors du rapprochement FFME : {e}")
        finally:
            conn.close()
        return prep

    @classmethod
    def apply_ffme_matches(cls, updates: list, season_name: str = None) -> bool:
        """
        Phase B de l'import FFME — écrit en base les associations validées :
        updates = [(match_type, licence, passeports, diplomas, document_sante, user_id), ...]
        Met à jour la licence/passeports/diplômes de l'utilisateur, écrit le Document de
        santé (associé à la personne pour la saison active, via purchases) et bascule
        ses achats de la saison active en statut "Terminé" (licence FFME confirmée).
        """
        if not updates:
            return True
        SqliteDatabase.create_db_backup()
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            from domain.constants import get_active_season
            target_season = str(season_name or get_active_season()).strip()

            for u in updates:
                lic = str(u[1] or "").strip()
                passp = str(u[2] or "").strip()
                dipl = str(u[3] or "").strip()
                uid = int(u[5])

                if passp and dipl:
                    cursor.execute("""
                        UPDATE users
                        SET licence_ffme = ?, raw_passports = ?, raw_diplomas = ?
                        WHERE id = ?
                    """, (lic, passp, dipl, uid))
                elif passp:
                    cursor.execute("""
                        UPDATE users
                        SET licence_ffme = ?, raw_passports = ?
                        WHERE id = ?
                    """, (lic, passp, uid))
                elif dipl:
                    cursor.execute("""
                        UPDATE users
                        SET licence_ffme = ?, raw_diplomas = ?
                        WHERE id = ?
                    """, (lic, dipl, uid))
                else:
                    cursor.execute("""
                        UPDATE users
                        SET licence_ffme = ?
                        WHERE id = ?
                    """, (lic, uid))

            cursor.executemany("""
                UPDATE purchases
                SET status = ?, status_normalized = ?, document_sante = ?, updated_at = ?
                WHERE user_id = ? AND order_id IN (
                    SELECT id FROM orders
                    WHERE season_id = (SELECT id FROM seasons WHERE name = ? OR is_active = 1 LIMIT 1)
                )
            """, [(u[0], schema_v2.normalize_status(u[0]), u[4],
                   datetime.datetime.now().isoformat(timespec="seconds"), u[5], target_season) for u in updates])
            conn.commit()
            return True
        except Exception as e:
            print(f"[SQLITE] Erreur lors de la fusion FFME en BDD : {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    @classmethod
    def merge_ffme_licensees(cls, excel_path: str) -> dict:
        """
        Import FFME non interactif (rétrocompatibilité / scripts) :
        rapprochement automatique + écriture directe, sans association manuelle.
        """
        prep = cls.prepare_ffme_licensees(excel_path)
        stats = prep["stats"]
        if not stats["errors"]:
            if not cls.apply_ffme_matches(prep["updates"]):
                stats["errors"].append("Erreur lors de la fusion en BDD.")
        stats["not_found"] = len(prep["unmatched"])
        return stats

    @classmethod
    def merge_autonomes_data(cls, excel_path: str) -> dict:
        """
        Phase 5 - Importe la liste d'autonomie (Autonomes_*.xlsx) et la fusionne avec
        les utilisateurs du schema v2 (badge rouge, autonomie bloc, passeports).
        """
        SqliteDatabase.create_db_backup()
        import pandas as pd
        from domain.utils import normalize_name

        stats = {"total_processed": 0, "matched": 0, "not_found": 0, "errors": []}

        if not os.path.exists(excel_path):
            stats["errors"].append(f"Fichier introuvable : {excel_path}")
            return stats
        try:
            df = pd.read_excel(excel_path, header=1)
            df = df.fillna("")
        except Exception as e:
            stats["errors"].append(f"Erreur de lecture Excel : {e}")
            return stats

        required_cols = ["N\u00b0 de licence", "Badge rouge diff", "Autonomie Bloc"]
        for col in required_cols:
            if col not in df.columns:
                stats["errors"].append(f"Colonne requise manquante dans le fichier Excel : {col}")
                return stats

        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, last_name, first_name, licence_ffme, raw_passports FROM users")
            users = [dict(row) for row in cursor.fetchall()]

            users_by_licence = {}
            for u in users:
                lic = str(u["licence_ffme"] or "").strip()
                if lic.endswith(".0"):
                    lic = lic[:-2]
                clean_lic = "".join(c for c in lic if c.isdigit())
                if clean_lic:
                    users_by_licence[clean_lic] = u

            users_by_name = {}
            for u in users:
                nk = normalize_name(u["last_name"])
                fk = normalize_name(u["first_name"])
                if nk and fk:
                    users_by_name[(nk, fk)] = u

            updates = []  # (badge_rouge, autonomie_bloc, raw_passports, user_id)
            file_badge_rouge_count = 0

            for idx, row in df.iterrows():
                stats["total_processed"] += 1
                raw_lic = str(row.get("N\u00b0 de licence", "")).strip()
                if raw_lic.endswith(".0"):
                    raw_lic = raw_lic[:-2]
                lic_num = "".join(c for c in raw_lic if c.isdigit())

                badge_rouge_raw = str(row.get("Badge rouge diff", "")).strip().upper()
                autonomie_bloc_raw = str(row.get("Autonomie Bloc", "")).strip().upper()
                if badge_rouge_raw == "X":
                    file_badge_rouge_count += 1
                badge_rouge = "Oui" if badge_rouge_raw == "X" else ("Non" if not badge_rouge_raw else row.get("Badge rouge diff", ""))
                autonomie_bloc = "Oui" if autonomie_bloc_raw == "X" else ("Non" if not autonomie_bloc_raw else row.get("Autonomie Bloc", ""))

                has_orange_raw = str(row.get("Passeport Orange", "")).strip().upper()
                orange_passport_val = "Escalade - Passeport orange" if has_orange_raw == "X" else ""

                matched = None
                if lic_num and lic_num in users_by_licence:
                    matched = users_by_licence[lic_num]
                if not matched:
                    nom_raw = str(row.get("NOM", "")).strip()
                    prenom_raw = str(row.get("Pr\u00e9nom", "")).strip()
                    if nom_raw and prenom_raw:
                        key = (normalize_name(nom_raw), normalize_name(prenom_raw))
                        if key in users_by_name:
                            matched = users_by_name[key]

                if matched:
                    existing_passports = str(matched.get("raw_passports") or "").strip()
                    if orange_passport_val and "orange" not in existing_passports.lower():
                        new_passports = f"{existing_passports}, {orange_passport_val}" if existing_passports else orange_passport_val
                    else:
                        new_passports = existing_passports
                    updates.append((badge_rouge, autonomie_bloc, new_passports, matched["id"]))
                    stats["matched"] += 1
                else:
                    stats["not_found"] += 1

            stats["file_badge_rouge_count"] = file_badge_rouge_count

            if updates:
                cursor.executemany("""
                    UPDATE users
                    SET badge_rouge = ?, autonomie_bloc = ?, raw_passports = ?
                    WHERE id = ?
                """, updates)
                conn.commit()

            cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE badge_rouge = 'Oui'")
            stats["db_total_badge_rouge"] = cursor.fetchone()["cnt"]
            cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE autonomie_bloc = 'Oui' AND (badge_rouge IS NULL OR badge_rouge != 'Oui')")
            stats["db_autonomes_without_badge_rouge"] = cursor.fetchone()["cnt"]
        except Exception as e:
            conn.rollback()
            stats["errors"].append(f"Erreur lors de la fusion en BDD : {e}")
        finally:
            conn.close()
        return stats
