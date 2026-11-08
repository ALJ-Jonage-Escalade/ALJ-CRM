"""Membership dashboard: HelloAsso registrations of the membership campaign (tariffs, map points)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from api.responses import error, error_responses
from domain.members.helloasso_membership import map_membership_items, parse_membership_campaign
from infrastructure.geocoding import geocode_missing_addresses
from infrastructure.helloasso import api as helloasso_api
from infrastructure.sqlite.geocache import GeocacheRepository
from services.members.helloasso_import import MembershipImportService

router = APIRouter()


def get_target_slug() -> str:
    """Slug of the membership campaign, the import's (MembershipImportService.campaign_reference). A reference that
    cannot be read gives its last URL segment, as before."""
    reference = MembershipImportService.campaign_reference()
    try:
        return parse_membership_campaign(reference).slug
    except ValueError:
        return [segment for segment in reference.split("/") if segment.strip()][-1]


@router.get("/api/dashboard", responses=error_responses(404, 502))
def get_dashboard_data(background_tasks: BackgroundTasks):
    """Route principale renvoyant toutes les données formatées pour le frontend. La campagne est celle de l'import
    des adhésions (get_target_slug) et les inscriptions sont lues par le même mapper.
    404: campaign unknown to HelloAsso; 502: HelloAsso could not be read completely (never a partial dashboard)."""
    target_slug = get_target_slug()
    try:
        campaigns = helloasso_api.get_campaigns()
        target_camp = next((c for c in campaigns if c.get('formSlug') == target_slug), None)
        if not target_camp:
            return error(404, f"Campagne HelloAsso introuvable : {target_slug}.", "helloasso_campaign_not_found")
        c_type = target_camp.get('formType')
        records = map_membership_items(helloasso_api.fetch_form_items(c_type, target_slug))
    except helloasso_api.HelloAssoApiError as e:
        return error(502, e.message, e.code)

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

    # Geocode the missing addresses after the answer
    if missing_addresses:
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
