import { describe, expect, it } from "vitest";
import {
  dayOptions,
  draftOf,
  filterSlots,
  icsDays,
  layoutDay,
  parseHours,
  planningIcs,
  slotError,
  slotKind,
  tarifOptions,
  typeOptions,
  updateOf,
  week,
  type Slot,
} from "./slots";

function slot(change: Partial<Slot> = {}): Slot {
  return {
    id: 1,
    groupe: "Loisir collège",
    type: "cours",
    categorie_age: "U12-U15",
    jour: "Lundi",
    horaires: "18:30 - 20:00",
    encadrants: ["Remus Lupin"],
    helloasso_tarifs: ["Loisir collège"],
    whatsapp_link: "",
    naissance_min: "",
    naissance_max: "",
    ...change,
  };
}

describe("hours", () => {
  it.each([
    ["18:00 - 20:00", [18, 20]],
    ["18h30-20h", [18.5, 20]],
    ["18h – 19h30", [18, 19.5]],
    ["17:00 18:00", [17, 18]],
    ["9:15 - 10:45", [9.25, 10.75]],
    ["20:00", null],
    ["20:00 - 18:00", null],
    ["le soir", null],
  ])("%s", (text, hours) => {
    expect(parseHours(text)).toEqual(hours);
  });
});

describe("week grid", () => {
  it("places a slot from 9:00, 50 pixels an hour", () => {
    expect(layoutDay([slot({ horaires: "10:00 - 12:00" })])).toMatchObject([{ top: 50, height: 96, lane: 0, lanes: 1 }]);
    expect(layoutDay([slot({ horaires: "9:00 - 9:15" })])[0]!.height).toBe(28);
  });

  it("puts overlapping slots side by side, and reuses a free lane", () => {
    const placed = layoutDay([
      slot({ id: 1, horaires: "18:00 - 20:00" }),
      slot({ id: 2, horaires: "19:00 - 21:00" }),
      slot({ id: 3, horaires: "20:00 - 22:00" }),
    ]);
    expect(placed.map((p) => [p.slot.id, p.lane, p.lanes])).toEqual([
      [1, 0, 2],
      [2, 1, 2],
      [3, 0, 2],
    ]);
  });

  it("leaves out unreadable hours, several days and Sunday", () => {
    const days = week([
      slot({ jour: "lundi" }),
      slot({ jour: "Lundi / Jeudi" }),
      slot({ jour: "Dimanche" }),
      slot({ jour: "Mardi", horaires: "?" }),
    ]);
    expect(days.map((d) => d.day)).toEqual(["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]);
    expect(days.map((d) => d.placed.length)).toEqual([1, 0, 0, 0, 0, 0]);
  });

  it("colours a slot by its type, or its name", () => {
    expect(slotKind({ type: "compétition", groupe: "U13" })).toBe("competition");
    expect(slotKind({ type: "cours", groupe: "Perfectionnement adultes" })).toBe("perfectionnement");
    expect(slotKind({ type: "autonome", groupe: "Autonome Bloc" })).toBe("autonome-bloc");
    expect(slotKind({ type: "autonome", groupe: "Autonome" })).toBe("autonome");
    expect(slotKind({ type: "", groupe: "Découverte" })).toBe("cours");
  });
});

describe("table filters", () => {
  const slots = [
    slot({ id: 1 }),
    slot({ id: 2, groupe: "Compétition U13", type: "compétition", categorie_age: "U11-U13", encadrants: ["Severus Snape"] }),
    slot({ id: 3, groupe: "Autonome Bloc", type: "autonome", helloasso_tarifs: ["Autonome bouldering"] }),
  ];
  const ids = (found: Slot[]) => found.map((s) => s.id);

  it("search every column, case ignored", () => {
    expect(ids(filterSlots(slots, " SNAPE ", "all"))).toEqual([2]);
    expect(ids(filterSlots(slots, "bouldering", "all"))).toEqual([3]);
    expect(ids(filterSlots(slots, "u12-u15", "all"))).toEqual([1, 3]);
  });

  it("keep a kind", () => {
    expect(ids(filterSlots(slots, "", "compétition"))).toEqual([2]);
    expect(ids(filterSlots(slots, "", "cours"))).toEqual([1]);
    expect(ids(filterSlots(slots, "", "all"))).toEqual([1, 2, 3]);
  });
});

describe("slot form", () => {
  it("starts a new slot on Monday evening", () => {
    expect(draftOf()).toMatchObject({ id: 0, jour: "Lundi", horaires: "18:00 - 20:00", type: "cours", encadrants: "" });
  });

  it("edits the coaches as one text", () => {
    const draft = draftOf(slot({ encadrants: ["Remus Lupin", "Rubeus Hagrid"] }));
    expect(draft.encadrants).toBe("Remus Lupin, Rubeus Hagrid");
    expect(updateOf({ ...draft, encadrants: " Remus Lupin,, Minerva McGonagall , " }).encadrants).toEqual([
      "Remus Lupin",
      "Minerva McGonagall",
    ]);
  });

  it("keeps the slot's own day, type and tariffs among the choices", () => {
    expect(dayOptions("Lundi")).toHaveLength(7);
    expect(dayOptions("Lundi / Jeudi").at(-1)).toBe("Lundi / Jeudi");
    expect(typeOptions("cours")).toHaveLength(6);
    expect(typeOptions("stage").at(-1)).toEqual(["stage", "stage"]);
    expect(tarifOptions(["A", "B"], ["B", "Ancien"])).toEqual(["A", "B", "Ancien"]);
  });

  it.each([
    [{}, null],
    [{ groupe: " " }, "⚠️ Le nom du groupe est obligatoire."],
    [{ horaires: "" }, "⚠️ Les horaires sont obligatoires."],
    [{ horaires: "le soir" }, "⚠️ Horaires illisibles : écrivez-les comme « 18:00 - 20:00 »."],
  ])("checks %j", (change, message) => {
    expect(slotError({ ...draftOf(slot()), ...change })).toBe(message);
  });
});

describe("planningIcs", () => {
  const now = new Date(2026, 9, 27, 10, 0);

  it("names every day of a slot", () => {
    expect(icsDays("Lundi / Jeudi")).toEqual(["MO", "TH"]);
    expect(icsDays("Mercredi")).toEqual(["WE"]);
    expect(icsDays("?")).toEqual([]);
  });

  it("starts each slot on its own day of the season, at its Paris times", () => {
    const { ics, skipped } = planningIcs([slot({ jour: "Mercredi", horaires: "17:00 - 18:30" })], now);
    expect(skipped).toBe(0);
    // 1 September 2026 is a Tuesday: the first Wednesday is the 2nd
    expect(ics).toContain("DTSTART;TZID=Europe/Paris:20260902T170000");
    expect(ics).toContain("DTEND;TZID=Europe/Paris:20260902T183000");
    expect(ics).toContain("RRULE:FREQ=WEEKLY;BYDAY=WE;UNTIL=20270630T215959Z");
    expect(ics).toContain("DTSTAMP:");
  });

  it("repeats a slot on all its days, escapes the text and leaves out unreadable slots", () => {
    const { ics, skipped } = planningIcs(
      [slot({ jour: "Lundi / Jeudi", groupe: "Autonome, adultes", encadrants: [] }), slot({ id: 2, horaires: "à voir" })],
      now,
    );
    expect(skipped).toBe(1);
    expect(ics).toContain("BYDAY=MO,TH");
    expect(ics).toContain("SUMMARY:ALJ Escalade — Autonome\\, adultes");
    expect(ics.match(/BEGIN:VEVENT/g)).toHaveLength(1);
  });
});
