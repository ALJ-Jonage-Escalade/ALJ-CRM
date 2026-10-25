/* Leaflet part of the members map (Outils page), loaded only when the map is first shown: Leaflet and markercluster
   stay out of the main bundle. Member data comes from the public HelloAsso form: the popups are built with
   textContent, never as HTML. The tiles come from OpenStreetMap France and Esri, the only third-party requests. */
import L from "leaflet";
import "leaflet.markercluster"; // after leaflet: the plugin extends the global L that Leaflet sets
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";
import iconUrl from "leaflet/dist/images/marker-icon.png";
import shadowUrl from "leaflet/dist/images/marker-shadow.png";
import type { MapPoint } from "./membersMap";

export interface MembersMapView {
  /** Replaces the markers, then fits the view to them. */
  show(points: readonly MapPoint[]): void;
  destroy(): void;
}

/** Jonage, the view before the first points. */
const CLUB: L.LatLngTuple = [45.795, 5.045];

// The default icon guesses its address from Leaflet's CSS, which the hashed file names of the build break
const MARKER = L.icon({
  iconUrl,
  iconRetinaUrl,
  shadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className: string, text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function popup(point: MapPoint): HTMLElement {
  const count = point.members.length;
  const content = element("div", "");
  content.dataset.testid = "map-popup";
  const list = element("ul", "m-0 list-disc pl-4 text-xs text-slate-800");
  list.append(...point.members.map((m) => element("li", "mb-0.5", `${m.name} (${m.group})`)));
  content.append(
    element("div", "mb-1 border-b border-slate-200 pb-0.5 text-sm font-bold text-club-blue", `${count} Adhérent${count > 1 ? "s" : ""}`),
    element("div", "mb-2 text-[11px] text-slate-500", `📍 ${point.address}`),
    list,
  );
  return content;
}

export function createMembersMapView(container: HTMLElement): MembersMapView {
  const map = L.map(container).setView(CLUB, 13);
  const osmFrance = L.tileLayer("https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png", {
    maxZoom: 20,
    attribution: '&copy; OpenStreetMap France | &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  });
  const esriStreets = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    attribution: "Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS",
  });
  osmFrance.addTo(map);
  L.control.layers({ "OpenStreetMap France": osmFrance, "Plan Esri": esriStreets }, undefined, { position: "topright" }).addTo(map);

  const markers = L.markerClusterGroup({ showCoverageOnHover: false, spiderfyOnMaxZoom: true });
  map.addLayer(markers);

  // The tab can be hidden (v-show) or resized: Leaflet must measure its container again
  const resizes = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => map.invalidateSize());
  resizes?.observe(container);

  return {
    show(points) {
      markers.clearLayers();
      markers.addLayers(points.map((p) => L.marker([p.lat, p.lon], { icon: MARKER }).bindPopup(() => popup(p))));
      const bounds = markers.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50] });
      }
    },
    destroy() {
      resizes?.disconnect();
      map.remove();
    },
  };
}
