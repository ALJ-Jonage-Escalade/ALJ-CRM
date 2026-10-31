"""Membership dashboard: HelloAsso registrations of the membership campaign (tariffs, map points)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks

from domain.competitions.matching import parse_campaign_identifier
from domain.constants import get_active_season
from domain.members.helloasso_membership import map_membership_items
from infrastructure.firestore.app_settings import HELLOASSO_MEMBERSHIP_CAMPAIGN, AppSettingsRepository
from infrastructure.firestore.client import FirestoreError
from infrastructure.geocoding import geocode_missing_addresses
from infrastructure.helloasso import api as helloasso_api
from infrastructure.security.secret_store import SecretStore
from infrastructure.sqlite.geocache import GeocacheRepository
from services.members.helloasso_import import MembershipImportService

logger = logging.getLogger("alj")

router = APIRouter()


def _chosen_membership_campaign() -> str:
    """Campaign chosen in Paramètres › Campagne HelloAsso, or "" (not chosen, Firestore unreadable)."""
    try:
        return (AppSettingsRepository.get(HELLOASSO_MEMBERSHIP_CAMPAIGN) or "").strip()
    except FirestoreError as e:
        logger.warning("Membership campaign setting unreadable, falling back to CAMPAIGN_SLUG: %s", e)
        return ""


def get_target_slug() -> str:
    """Slug de la campagne d'adhésion, lu à chaque appel (un changement s'applique sans redémarrage).

    Ordre : réglage Firestore HELLOASSO_MEMBERSHIP_CAMPAIGN, puis variable CAMPAIGN_SLUG, puis le slug
    par défaut de la saison (ces deux derniers sont un repli temporaire)."""
    ref = _chosen_membership_campaign() or (SecretStore.get_secret("CAMPAIGN_SLUG") or "").strip()
    if not ref:
        return f"adhesion-escalade-{get_active_season()}-amicale-laique-escalade-2"
    try:
        return parse_campaign_identifier(ref)["slug"]
    except ValueError:
        # Unrecognised URL: its last segment, as before
        return [segment for segment in ref.split("/") if segment.strip()][-1]


@router.get("/api/dashboard")
def get_dashboard_data(background_tasks: BackgroundTasks = None, force_refresh: bool = False):
    """Route principale renvoyant toutes les données formatées pour le frontend. La campagne est celle de l'import
    des adhésions (MembershipImportService.campaign) et les inscriptions sont lues par le même mapper."""
    print("-> Interrogation de l'API HelloAsso...")

    campaigns = helloasso_api.get_campaigns()
    target_slug = MembershipImportService.campaign().slug
    target_camp = next((c for c in campaigns if c.get('formSlug') == target_slug), None)

    if not target_camp:
        return {"error": "Campagne introuvable"}

    c_type = target_camp.get('formType')
    records = map_membership_items(helloasso_api.get_items(c_type, target_slug))

    participants = []
    tariffs_count = {}
    map_data_dict = {}

    # Charger le cache géographique depuis SQLite
    geocache = GeocacheRepository.get_geocache()
    missing_addresses = set()

    for record in records:
        flat_item = record.legacy_fields()
        fields = {name.lower(): value.strip() for name, value in record.custom_fields.items()}
        city = fields.get("ville", "").upper()
        zip_code = fields.get("code postal", "")
        address = next((value for name, value in fields.items() if "adresse" in name and "rue" in name), "")

        flat_item["city"] = city
        flat_item["address"] = address
        flat_item["zip"] = zip_code

        # Résoudre l'adresse complète du membre
        full_address = ""
        if address and city:
            full_address = f"{address}, {zip_code}, {city}, France"
        elif city:
            full_address = f"{city}, {zip_code}, France"
        
        flat_item["full_address"] = full_address

        lat, lon = None, None
        if full_address:
            if full_address in geocache:
                coords = geocache[full_address]
                lat, lon = coords[0], coords[1]
            else:
                missing_addresses.add(full_address)
        
        flat_item["lat"] = lat
        flat_item["lon"] = lon

        # Résoudre également au niveau de la ville seule (statistiques de secours)
        city_address = f"{city}, {zip_code}, France" if city else ""
        city_lat, city_lon = None, None
        if city_address:
            if city_address in geocache:
                city_coords = geocache[city_address]
                city_lat, city_lon = city_coords[0], city_coords[1]
            else:
                missing_addresses.add(city_address)
        
        flat_item["city_lat"] = city_lat
        flat_item["city_lon"] = city_lon

        participants.append(flat_item)
        
        # Comptage par Tarif
        t_name = flat_item["tarif_name"]
        tariffs_count[t_name] = tariffs_count.get(t_name, 0) + 1
        
        # Préparation des données Cartographiques (Groupement par coordonnées exactes)
        if lat is not None and lon is not None:
            addr_key = f"{lat:.6f},{lon:.6f}"
            if addr_key not in map_data_dict:
                map_data_dict[addr_key] = {
                    "address": full_address,
                    "city": city,
                    "zip": zip_code,
                    "lat": lat,
                    "lon": lon,
                    "count": 0,
                    "members": [],
                    "groups": set()
                }
            map_data_dict[addr_key]["count"] += 1
            map_data_dict[addr_key]["members"].append(f"{flat_item['user_firstName']} {flat_item['user_lastName']} ({t_name})")
            map_data_dict[addr_key]["groups"].add(t_name)

    # S'il y a des adresses manquantes et un gestionnaire de tâches de fond, lancer le géocodage
    if missing_addresses and background_tasks:
        background_tasks.add_task(geocode_missing_addresses, list(missing_addresses))

    # Convertir le set des groupes en liste pour la sérialisation JSON
    for data in map_data_dict.values():
        data["groups"] = list(data["groups"])

    map_data = list(map_data_dict.values())
    tariffs = [{"name": k, "count": v} for k, v in tariffs_count.items()]

    dashboard_data = {
        "campaign": target_camp,
        "total_inscrits": len(participants),
        "participants": participants,
        "tariffs": tariffs,
        "map_data": map_data
    }

    return dashboard_data
