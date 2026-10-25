import { afterEach, describe, expect, it } from "vitest";
import type { MapPoint } from "./membersMap";
import { createMembersMapView } from "./membersMapView";

// Member data comes from the public HelloAsso form: a name, a tariff or an address can hold markup
const HOSTILE = `<img src=x onerror="window.hacked=1">"'&</script><b>`;
const POINT: MapPoint = { address: HOSTILE, lat: 45.795, lon: 5.045, members: [{ name: HOSTILE, group: HOSTILE }] };

afterEach(() => {
  document.body.innerHTML = "";
});

describe("createMembersMapView", () => {
  it("shows member data in the popups as text, never as HTML", () => {
    const container = document.createElement("div");
    // jsdom has no layout: Leaflet measures the map with clientWidth/clientHeight, and draws nothing in a 0×0 map
    Object.defineProperties(container, { clientWidth: { value: 800 }, clientHeight: { value: 600 } });
    document.body.append(container);
    const view = createMembersMapView(container);
    view.show([POINT]);

    const marker = container.querySelector<HTMLElement>(".leaflet-marker-icon");
    expect(marker).not.toBeNull();
    marker!.click();
    const popup = container.querySelector<HTMLElement>('[data-testid="map-popup"]');
    expect(popup).not.toBeNull();

    expect(popup!.querySelectorAll("img, b, script")).toHaveLength(0);
    expect(popup!.textContent).toContain(`📍 ${HOSTILE}`);
    expect([...popup!.querySelectorAll("li")].map((li) => li.textContent)).toEqual([`${HOSTILE} (${HOSTILE})`]);
    expect("hacked" in window).toBe(false);
    view.destroy();
  });
});
