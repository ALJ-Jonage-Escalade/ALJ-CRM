import { describe, expect, it } from "vitest";
import { decisionsOf, initialChoices, memberHref, type MembershipPreview, type MembershipRow } from "./helloassoImport";

const ROW = (item_id: number, bucket: MembershipRow["bucket"]): MembershipRow => ({
  item_id,
  bucket,
  reason: "",
  order_ref: String(500 + item_id),
  order_date: "",
  last_name: "WEASLEY",
  first_name: "Ginny",
  birth_date: "2013-08-11",
  licence: "",
  tarif_name: "Loisir",
  amount: 150,
  status: "Processed",
  candidates: [],
  can_create: true,
});
const PREVIEW: MembershipPreview = {
  status: "success",
  season: "2026-2027",
  campaign: "adhesion-escalade-2026-2027",
  blocked_reason: null,
  counts: { already_imported: 1, new: 1, renewal: 1, updated: 1, to_review: 1, blocked: 1 },
  rows: [ROW(1, "new"), ROW(2, "renewal"), ROW(3, "updated"), ROW(4, "to_review"), ROW(5, "already_imported"), ROW(6, "blocked")],
};

describe("HelloAsso membership import", () => {
  it("pre-checks the new, renewal and changed rows; the rows to review start skipped", () => {
    expect(initialChoices(PREVIEW)).toEqual({ 1: "import", 2: "import", 3: "import", 4: "skip" });
  });

  it("sends a decision with its bucket for every row that has a choice", () => {
    expect(decisionsOf(PREVIEW, { 1: "import", 2: "skip", 4: "skip" })).toEqual({
      1: { bucket: "new", choice: "import" },
      2: { bucket: "renewal", choice: "skip" },
      4: { bucket: "to_review", choice: "skip" },
    });
  });

  it("links an imported member to their record in Adhérents", () => {
    expect(memberHref({ user_id: 7, purchase_id: 12 }, "2026-2027")).toBe("/bureau/adherents?id=7&saison=2026-2027&achat=12");
  });
});
