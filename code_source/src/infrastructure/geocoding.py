"""Address geocoding (Nominatim / OpenStreetMap), cached in the SQLite geocache table."""

from __future__ import annotations

import time
from typing import List

from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.sqlite.geocache import GeocacheRepository


def geocode_missing_addresses(addresses: List[str]) -> None:
    """Géocode les adresses manquantes en tâche de fond avec limitation stricte de débit."""
    print(f"🌍 [GEOCODING] Début du géocodage en tâche de fond pour {len(addresses)} adresses...")
    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="alj_escalade_manager")
    except Exception as e:
        print(f"❌ [GEOCODING] Impossible de charger geopy/Nominatim : {e}")
        return

    for i, address in enumerate(addresses):
        # Pause de 1.5s entre chaque appel pour respecter les CGU Nominatim
        time.sleep(1.5)
        try:
            # Members' addresses and coordinates are personal data: never in the logs
            print(f"🌍 [GEOCODING] ({i+1}/{len(addresses)}) Recherche d'une adresse…")
            location = geolocator.geocode(address, timeout=10)
            if location:
                lat, lon = location.latitude, location.longitude
                print("✅ [GEOCODING] Adresse localisée.")
                GeocacheRepository.save_geocode(address, lat, lon)
            else:
                print("⚠️ [GEOCODING] Adresse non résolue.")
                # Enregistrer des coordonnées nulles pour éviter de requêter indéfiniment cette mauvaise adresse
                GeocacheRepository.save_geocode(address, None, None)
        except Exception as e:
            print(f"❌ [GEOCODING] Erreur lors du géocodage de l'adresse {i+1} : {type(e).__name__}")
    if CloudDatabase.is_enabled():
        CloudDatabase.flush_only()
    print("🌍 [GEOCODING] Tâche de fond terminée.")
