"""Address geocoding (Nominatim / OpenStreetMap), cached in the SQLite geocache table."""

from __future__ import annotations

import time
from typing import List

from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.sqlite.repository import SqliteRepository


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
            print(f"🌍 [GEOCODING] ({i+1}/{len(addresses)}) Recherche de l'adresse : {address}")
            location = geolocator.geocode(address, timeout=10)
            if location:
                lat, lon = location.latitude, location.longitude
                print(f"✅ [GEOCODING] Trouvé : {lat}, {lon}")
                SqliteRepository.save_geocode(address, lat, lon)
            else:
                print(f"⚠️ [GEOCODING] Adresse non résolue : {address}")
                # Enregistrer des coordonnées nulles pour éviter de requêter indéfiniment cette mauvaise adresse
                SqliteRepository.save_geocode(address, None, None)
        except Exception as e:
            print(f"❌ [GEOCODING] Erreur lors du géocodage de '{address}' : {e}")
    if CloudDatabase.is_enabled():
        CloudDatabase.flush_only()
    print("🌍 [GEOCODING] Tâche de fond terminée.")
