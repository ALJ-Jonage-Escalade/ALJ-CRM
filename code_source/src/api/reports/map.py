"""Members map (Leaflet), from the SQLite cache; missing addresses are geocoded in the background."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import HTMLResponse

from domain.utils import json_for_script
from infrastructure.geocoding import geocode_missing_addresses

router = APIRouter()


def get_sqlite_map_data(background_tasks: BackgroundTasks = None) -> List[Dict[str, Any]]:
    """Génère les points cartographiques directement depuis la base SQLite (Source unique de vérité)."""
    try:
        from infrastructure.sqlite.geocache import GeocacheRepository
        from infrastructure.sqlite.members import MemberRepository
        raw_data = MemberRepository.load_direct_data()
        
        map_data_dict = {}
        geocache = GeocacheRepository.get_geocache()
        missing_addresses = set()
        
        for row in raw_data:
            # Ignorer les annulés pour la carte
            status = row.get("status", "Validé")
            if "annul" in str(status).lower():
                continue
                
            firstName = (row.get("first_name") or "").strip().title()
            lastName = (row.get("last_name") or "").strip().upper()
            t_name = row.get("tarif_name") or "".strip() or "Aucun"
            
            addr = row.get("address") or ""
            city = row.get("city") or ""
            zip_code = row.get("zip_code") or ""
            
            # Formater l'adresse de façon normalisée et insensible à la casse
            from domain.utils import clean_city_name
            city_clean = clean_city_name(city)
            city_upper = city_clean.upper()
            addr_clean = str(addr).strip() if addr else ""
            zip_clean = str(zip_code).strip() if zip_code else ""
            
            full_address = ""
            if addr_clean and city_upper:
                full_address = f"{addr_clean}, {zip_clean}, {city_upper}, France"
            elif city_upper:
                full_address = f"{city_upper}, {zip_clean}, France"
                
            full_address = " ".join(full_address.split())
            if not full_address or full_address == "France":
                continue
                
            lat, lon = None, None
            if full_address in geocache:
                coords = geocache[full_address]
                lat, lon = coords[0], coords[1]
            else:
                # Si l'adresse contient un nom de rue, on tente de la géocoder en tâche de fond
                missing_addresses.add(full_address)
                
            if lat is not None and lon is not None:
                addr_key = f"{lat:.6f},{lon:.6f}"
                if addr_key not in map_data_dict:
                    map_data_dict[addr_key] = {
                        "address": f"{addr_clean}, {zip_clean} {city_upper}" if addr_clean else city_upper,
                        "city": city_upper,
                        "zip": zip_clean,
                        "lat": lat,
                        "lon": lon,
                        "count": 0,
                        "members": [],
                        "groups": set()
                    }
                map_data_dict[addr_key]["count"] += 1
                map_data_dict[addr_key]["members"].append(f"{firstName} {lastName} ({t_name})")
                map_data_dict[addr_key]["groups"].add(t_name)

        # Lancer le géocodage asynchrone pour les adresses manquantes en tâche de fond !
        if missing_addresses and background_tasks:
            background_tasks.add_task(geocode_missing_addresses, list(missing_addresses))

        # Convertir les sets en listes pour JSON
        for data in map_data_dict.values():
            data["groups"] = list(data["groups"])
            
        return list(map_data_dict.values())
        
    except Exception as e:
        print(f"⚠️ Erreur lors de la génération cartographique SQLite : {e}")
        return []

@router.get("/map", response_class=HTMLResponse)
def get_map(background_tasks: BackgroundTasks):
    """Renvoie la page de cartographie Leaflet interactive branchée sur SQLite."""
    map_points = get_sqlite_map_data(background_tasks)
    map_points_json = json_for_script(map_points)

    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>ALJ Escalade - Cartographie des Adhérents</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- CDN Leaflet -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    
    <!-- CDN Leaflet MarkerCluster -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.4.1/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.4.1/dist/MarkerCluster.Default.css" />
    <script src="https://unpkg.com/leaflet.markercluster@1.4.1/dist/leaflet.markercluster.js"></script>
    
    <style>
        html, body {
            height: 100%;
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #F8FAFC;
        }
        #header {
            background-color: #163A5F;
            color: white;
            padding: 10px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            height: 50px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            position: relative;
            z-index: 1000;
        }
        #header h1 {
            margin: 0;
            font-size: 18px;
            font-weight: 600;
        }
        .header-controls {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .multiselect {
            position: relative;
            user-select: none;
            width: 250px;
        }
        .selectBox {
            position: relative;
            cursor: pointer;
        }
        .selectBox select {
            width: 100%;
            padding: 6px 12px;
            border-radius: 4px;
            border: 1px solid #CBD5E1;
            font-size: 13px;
            background-color: white;
            color: #1E293B;
            outline: none;
            font-weight: bold;
            cursor: pointer;
            appearance: none;
            -webkit-appearance: none;
            -moz-appearance: none;
        }
        .overSelect {
            position: absolute;
            left: 0;
            right: 0;
            top: 0;
            bottom: 0;
        }
        #checkboxes {
            display: none;
            position: absolute;
            background-color: white;
            border: 1px solid #CBD5E1;
            border-radius: 4px;
            max-height: 400px;
            overflow-y: auto;
            z-index: 2000;
            width: 100%;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            color: #1E293B;
            top: 100%;
            right: 0;
            margin-top: 2px;
        }
        #checkboxes label {
            display: flex;
            align-items: center;
            padding: 8px 10px;
            font-size: 13px;
            cursor: pointer;
            border-bottom: 1px solid #F1F5F9;
            margin: 0;
        }
        #checkboxes label:hover {
            background-color: #F8FAFC;
        }
        #checkboxes input {
            margin-right: 8px;
            cursor: pointer;
        }
        #header .stats {
            font-size: 13px;
            background-color: rgba(255,255,255,0.15);
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: bold;
        }
        #map {
            height: calc(100% - 70px);
            width: 100%;
        }
        .popup-title {
            font-weight: bold;
            color: #163A5F;
            font-size: 14px;
            margin-bottom: 5px;
            border-bottom: 1px solid #E2E8F0;
            padding-bottom: 3px;
        }
        .popup-address {
            color: #64748B;
            font-size: 11px;
            margin-bottom: 8px;
        }
        .popup-members-list {
            margin: 0;
            padding-left: 15px;
            font-size: 12px;
            color: #1E293B;
        }
        .popup-members-list li {
            margin-bottom: 2px;
        }
    </style>
</head>
<body>

    <div id="header">
        <h1>📍 Cartographie ALJ Escalade</h1>
        <div class="header-controls">
            <div class="multiselect">
                <div class="selectBox" onclick="toggleCheckboxes()">
                    <select>
                        <option id="dropdown-title">🧗 Tous les groupes</option>
                    </select>
                    <div class="overSelect"></div>
                </div>
                <div id="checkboxes">
                    <!-- Checkboxes injéctées ici par le JS -->
                </div>
            </div>
            <div class="stats" id="stats-badge">Chargement...</div>
        </div>
    </div>

    <div id="map"></div>

    <script>
        // Injecter les données de cartographie générées côté serveur
        const mapData = {MAP_DATA_JSON};

        // Member data comes from the public HelloAsso form: always escaped before HTML insertion
        const escHtml = s => (s == null ? "" : String(s)).replace(/[&<>"']/g,
            c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

        // Fermer le menu si clic en dehors
        let expanded = false;
        document.addEventListener('click', function(event) {
            const multiselect = document.querySelector('.multiselect');
            if (expanded && !multiselect.contains(event.target)) {
                document.getElementById("checkboxes").style.display = "none";
                expanded = false;
            }
        });

        function toggleCheckboxes() {
            const checkboxes = document.getElementById("checkboxes");
            if (!expanded) {
                checkboxes.style.display = "block";
                expanded = true;
            } else {
                checkboxes.style.display = "none";
                expanded = false;
            }
        }

        // Extraire tous les groupes uniques pour peupler le menu déroulant
        const allGroups = new Set();
        mapData.forEach(point => {
            if (point.groups) {
                point.groups.forEach(g => allGroups.add(g));
            }
        });
        
        const checkboxesContainer = document.getElementById('checkboxes');
        
        // Option "Tous les groupes"
        const allLabel = document.createElement('label');
        allLabel.innerHTML = `<input type="checkbox" id="check-all" value="ALL" checked onchange="handleAllChange()"> <b>🧗 Sélectionner Tout</b>`;
        checkboxesContainer.appendChild(allLabel);

        Array.from(allGroups).sort().forEach(group => {
            const label = document.createElement('label');
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.className = 'group-checkbox';
            cb.value = group;
            cb.checked = true;
            cb.addEventListener('change', applyFilter);
            label.append(cb, ' ' + group);
            checkboxesContainer.appendChild(label);
        });

        function handleAllChange() {
            const checkAll = document.getElementById('check-all').checked;
            const cbs = document.querySelectorAll('.group-checkbox');
            cbs.forEach(cb => cb.checked = checkAll);
            applyFilter();
        }

        // Initialiser la carte Leaflet centrée par défaut sur Jonage
        const map = L.map('map').setView([45.795, 5.045], 13);

        // Fond de carte OpenStreetMap France (100% libre, gratuit, sans clé API ni filigrane)
        const osmFr = L.tileLayer('https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png', {
            maxZoom: 20,
            attribution: '&copy; OpenStreetMap France | &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        });

        // Fond alternatif Esri World Street Map (ultra-rapide, sans clé API)
        const esriStreet = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 19,
            attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS'
        });

        osmFr.addTo(map);

        L.control.layers({
            "OpenStreetMap France": osmFr,
            "Plan Esri": esriStreet
        }, null, { position: 'topright' }).addTo(map);

        let markers = L.markerClusterGroup({
            showCoverageOnHover: false,
            spiderfyOnMaxZoom: true
        });
        map.addLayer(markers);

        function renderMap(selectedGroups, allChecked) {
            markers.clearLayers();
            let totalMembersOnMap = 0;
            let totalUniqueLocations = 0;

            mapData.forEach(point => {
                if (point.lat && point.lon) {
                    
                    // Filtrage : est-ce que ce foyer possède un membre appartenant à l'un des groupes cochés ?
                    let membersToDisplay = point.members;
                    if (!allChecked) {
                        if (selectedGroups.length === 0) {
                            return; // Ignorer car aucun groupe
                        }
                        membersToDisplay = point.members.filter(m => {
                            return selectedGroups.some(g => m.includes(`(${g})`));
                        });
                        if (membersToDisplay.length === 0) {
                            return; // Ignorer cette adresse car personne ne correspond aux filtres
                        }
                    }

                    totalUniqueLocations++;
                    totalMembersOnMap += membersToDisplay.length;

                    // Créer un marqueur
                    const marker = L.marker([point.lat, point.lon]);

                    // Contenu du Popup stylisé
                    const popupContent = `
                        <div class="popup-title">${membersToDisplay.length} Adhérent${membersToDisplay.length > 1 ? 's' : ''}</div>
                        <div class="popup-address">📍 ${escHtml(point.address)}</div>
                        <ul class="popup-members-list">
                            ${membersToDisplay.map(name => `<li>${escHtml(name)}</li>`).join('')}
                        </ul>
                    `;

                    marker.bindPopup(popupContent);
                    markers.addLayer(marker);
                }
            });

            // Ajuster la vue de la carte pour englober tous les marqueurs si présents
            const groupBounds = markers.getBounds();
            if (groupBounds.isValid()) {
                map.fitBounds(groupBounds, { padding: [50, 50] });
            }

            // Mettre à jour le badge du header
            const suffix = allChecked ? '' : ` (Filtre: ${selectedGroups.length} groupe(s))`;
            document.getElementById('stats-badge').innerText = `${totalMembersOnMap} adhérents répartis sur ${totalUniqueLocations} adresses${suffix}`;
        }

        function applyFilter(event) {
            const checkAllCb = document.getElementById('check-all');
            const cbs = document.querySelectorAll('.group-checkbox');
            
            let selectedGroups = [];
            let allChecked = true;
            
            cbs.forEach(cb => {
                if (cb.checked) {
                    selectedGroups.push(cb.value);
                } else {
                    allChecked = false;
                }
            });
            
            // Sync the "All" checkbox state safely
            if (checkAllCb.checked !== allChecked && event && event.target.id !== 'check-all') {
                 checkAllCb.checked = allChecked;
            }

            // Update dropdown title
            const title = document.getElementById('dropdown-title');
            if (allChecked || selectedGroups.length === cbs.length) {
                title.innerText = "🧗 Tous les groupes";
            } else if (selectedGroups.length === 0) {
                title.innerText = "⚠️ Aucun groupe sélectionné";
            } else {
                title.innerText = `🧗 ${selectedGroups.length} groupe(s) filtré(s)`;
            }

            renderMap(selectedGroups, allChecked);
        }

        // Rendu initial (Tous les groupes)
        applyFilter();
    </script>
</body>
</html>
""".replace("{MAP_DATA_JSON}", map_points_json)
    return HTMLResponse(content=html_content)
