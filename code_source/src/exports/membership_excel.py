import logging
import os
import glob
import pandas as pd
import datetime
import csv

from paths import ROOT_DIR
from domain.members.sex import parse_sex
from domain.members.view import is_cancelled
from infrastructure.mail.senders import CLUB_CONTACT_EMAIL

logger = logging.getLogger("alj")

def parse_date_to_datetime(val):
    if not val or pd.isna(val):
        return ""
    # Si c'est déjà un timestamp ou datetime
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime()
    if isinstance(val, (datetime.datetime, datetime.date)):
        if isinstance(val, datetime.date) and not isinstance(val, datetime.datetime):
            return datetime.datetime(val.year, val.month, val.day)
        return val
        
    val_str = str(val).strip()
    if not val_str:
        return ""
        
    # Essayer de parser différents formats de chaînes courants
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%y", "%Y-%m-%d %H:%M:%S"):
        try:
            # Pour l'ISO-8601 complet (avec millisecondes et décalage)
            if "T" in val_str and fmt == "%Y-%m-%dT%H:%M:%S":
                return datetime.datetime.strptime(val_str[:19], fmt)
            return datetime.datetime.strptime(val_str, fmt)
        except ValueError:
            pass
            
    # Si on n'a pas réussi à parser mais que c'est une chaîne non vide, on la renvoie brute
    return val_str

def clean_digits_only(val):
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        if pd.isna(val):
            return ""
        try:
            return str(int(float(val)))
        except (ValueError, TypeError):
            return ""
    val_str = str(val).strip()
    if not val_str:
        return ""
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    return "".join(c for c in val_str if c.isdigit())



def generate_ffme_csv(participants_data, output_path=None, include_termine=False):
    """
    Génère le CSV d'import FFME.
    Si output_path est fourni (tests de non-régression), écrit à cet emplacement exact
    sans horodatage ni archivage. Sinon, comportement historique : fichier horodaté
    dans exports/ffme/ avec archivage des anciens CSV.
    Si include_termine est True, inclut également les adhérents dont le statut est 'Terminé'.
    """
    print("\nGénération simultanée du fichier CSV FFME...")
    if output_path:
        csv_path = output_path
        out_dir = os.path.dirname(os.path.abspath(csv_path))
        os.makedirs(out_dir, exist_ok=True)
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"import_ffme_{timestamp}.csv"

        root_dir = ROOT_DIR
        ffme_dir = os.path.join(root_dir, "exports", "ffme")
        os.makedirs(ffme_dir, exist_ok=True)
        csv_path = os.path.join(ffme_dir, csv_filename)

        # Archiver les anciens fichiers import_ffme
        archive_dir = os.path.join(ffme_dir, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        import shutil
        for old_file in glob.glob(os.path.join(ffme_dir, "import_ffme_*.csv")):
            if os.path.basename(old_file) != csv_filename:
                try:
                    shutil.move(old_file, os.path.join(archive_dir, os.path.basename(old_file)))
                    print(f"📦 Ancien fichier CSV FFME archivé : {os.path.basename(old_file)}")
                except Exception:
                    logger.warning("Archivage de l'ancien CSV FFME impossible : %s", old_file, exc_info=True)
    
    headers = [
        "numero de licence", "nom", "prenom", "date de naissance", "sexe", "nationalite",
        "adresse", "adresse complement", "code postal", "ville", "pays", "tel fixe", "tel mobile", 
        "courriel", "courriel 2", "pap nom", "pap prenom", "pap telephone", "pap courriel", 
        "nom de naissance", "commune de naissance", "departement de naissance", "type licence", 
        "assurance", "option ski", "option slackline", "option trail", "option vtt", 
        "assurance complementaire", "option protection agression"
    ]

    csv_rows = []
    ignored_members = []

    for p in participants_data:
        # Phase 6 — Normalisation NULL : les valeurs None du schéma v2 (vue legacy) sont
        # converties en chaîne vide AVANT traitement, supprimant les artefacts str(None)
        # historiques ('NO' pays, 'none' courriel 2, 'NONE' pap, 'None' adresse/ville).
        p = {k: (v if v is not None else "") for k, v in p.items()}

        # Exclure les listes d'attente, montants nuls (sauf les ajouts manuels), commandes annulées/canceled ou déjà validées (terminé si non demandé)
        tarif_name = str(p.get("tarif_name", "")).lower()
        amount = p.get("amount", 0.0)
        status = str(p.get("status", "")).lower()
        commentaires = str(p.get("commentaires_correctif", "")).lower()
        is_manual = "ajout manuel" in commentaires
        
        if "attente" in tarif_name or (amount == 0.0 and not is_manual) or is_cancelled(status):
            continue
        if not include_termine and "termin" in status:
            continue

        nom = str(p.get("last_name", "")).strip().upper()
        if not nom: nom = "INCONNU"

        prenom = str(p.get("first_name", "")).strip()
        if not prenom: prenom = "INCONNU"

        # 1. Licence
        lic_num = clean_digits_only(p.get("licence_ffme", ""))
        if len(lic_num) < 5 or len(lic_num) > 10:
            lic_num = ""

        # 2. DOB
        dob_val = p.get("birth_date", "")
        dob_date = None
        if isinstance(dob_val, (datetime.datetime, datetime.date)):
            dob_date = dob_val
        else:
            dob_str = str(dob_val).strip()
            parsed_dt = parse_date_to_datetime(dob_str)
            if isinstance(parsed_dt, (datetime.datetime, datetime.date)):
                dob_date = parsed_dt

        if not dob_date or dob_date >= datetime.datetime.now():
            ignored_members.append(f"⚠️ [IGNORÉ] {nom} {prenom} (Commande {p.get('order_ref')}) : date de naissance absente ou invalide ('{dob_val}')")
            continue
            
        dob = dob_date.strftime("%d/%m/%Y")
            
        # 3. Sexe : obligatoire pour une première licence (jamais deviné), vide accepté pour un renouvellement
        sex = parse_sex(p.get("sex"))
        if sex is None and not lic_num:
            ignored_members.append(f"⚠️ [IGNORÉ] {nom} {prenom} (Commande {p.get('order_ref')}) : sexe non renseigné")
            continue
        sexe = sex.value if sex else ""
            
        # 4. Pays
        pays_raw = str(p.get("country", "France")).strip().upper()
        pays = "FR" if "FR" in pays_raw or pays_raw == "FRANCE" or pays_raw == "" else pays_raw[:2]
        if not pays and not lic_num:
            pays = "FR"
            
        # 5. Nationalité
        nat_raw = str(p.get("nationality", "Francaise")).strip().upper()
        if "FR" in nat_raw or nat_raw == "FRANCE" or nat_raw == "":
            nat = "FR"
        elif "SUED" in nat_raw or "SWE" in nat_raw:
            nat = "SE"
        elif len(nat_raw) == 2:
            nat = nat_raw
        else:
            nat = "FR" if not lic_num else ""
            
        # 6. Adresse
        adresse = str(p.get("address", "")).strip()[:255]
        if not adresse and not lic_num:
            adresse = "ADRESSE NON COMMUNIQUEE"
            
        # 7. Code postal
        cp = clean_digits_only(p.get("zip_code", ""))
        if pays == "FR":
            if cp:
                cp = cp.zfill(5)[:5]
            else:
                cp = "69330" if not lic_num else ""
        else:
            cp = cp[:10]
            
        # 8. Ville
        ville = str(p.get("city", "")).strip().upper()[:100]
        if not ville and not lic_num:
            ville = "JONAGE"
            
        # 9. Téléphones
        tel_raw = clean_digits_only(p.get("phone", ""))
        if pays == "FR" and tel_raw:
            if tel_raw.startswith("33"):
                tel_raw = "0" + tel_raw[2:]
            tel_raw = tel_raw[:10]
        tel = tel_raw
        
        # 10. Courriels
        email = str(p.get("email_primary", "")).strip().lower()[:100]
        if not email:
            email = str(p.get("payer_email", "")).strip().lower()[:100]
        if not email and not lic_num:
            email = CLUB_CONTACT_EMAIL
            
        email2 = str(p.get("email_secondary", "")).strip().lower()[:100]
        
        # 11. PAP
        pap_raw = str(p.get("emergency1_name", "")).strip()
        pap_nom = ""
        pap_prenom = ""
        if pap_raw:
            if " " in pap_raw:
                parts = pap_raw.split(" ", 1)
                pap_prenom = parts[0][:100]
                pap_nom = parts[1].upper()[:100]
            else:
                pap_nom = pap_raw.upper()[:100]
                
        pap_tel = clean_digits_only(p.get("emergency1_phone", ""))[:15]
        
        # 12. Type licence (J, A, F)
        is_tribu = str(p.get("is_tribe", "")).lower()
        if is_tribu in ("true", "vrai", "oui", "1"):
            type_licence = "F"
        else:
            cutoff_date = datetime.datetime(2009, 8, 31)
            if dob_date > cutoff_date:
                type_licence = "J"
            else:
                type_licence = "A"
                
        # 13. Assurance (RC, B, B+, B++)
        val_ass_base = str(p.get("opt_Assurance Base", "Non")).upper()
        val_ass_plus = str(p.get("opt_Assurance Base +", "Non")).upper()
        val_ass_plusplus = str(p.get("opt_Assurance Base ++", "Non")).upper()
        
        if val_ass_plusplus in ("OUI", "TRUE", "VRAI"):
            assurance = "B++"
        elif val_ass_plus in ("OUI", "TRUE", "VRAI"):
            assurance = "B+"
        elif val_ass_base in ("OUI", "TRUE", "VRAI"):
            assurance = "B"
        else:
            assurance = "RC"
            
        # 14. Options
        val_ski = str(p.get("opt_Assurance Option ski de piste", "Non")).upper()
        opt_ski = "OUI" if val_ski in ("OUI", "TRUE", "VRAI") else "NON"
        
        val_vtt = str(p.get("opt_Assurance Option VTT", "Non")).upper()
        opt_vtt = "OUI" if val_vtt in ("OUI", "TRUE", "VRAI") else "NON"
        
        val_trail = str(p.get("opt_Assurance Option Trail", "Non")).upper()
        opt_trail = "OUI" if val_trail in ("OUI", "TRUE", "VRAI") else "NON"
        
        row = [
            lic_num, nom, prenom, dob, sexe, nat, adresse, "", cp, ville, pays, "", tel, 
            email, email2, pap_nom, pap_prenom, pap_tel, "", "", "", "", type_licence, 
            assurance, opt_ski, "NON", opt_trail, opt_vtt, "NON", "NON"
        ]
        csv_rows.append(row)
        
    from exports.spreadsheet_safety import csv_safe
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(headers)
        # Member data must never be evaluated as a formula when the file is opened
        writer.writerows([[csv_safe(v) for v in row] for row in csv_rows])
        
    print(f"Fichier CSV FFME généré : {csv_path}")
    return ignored_members













