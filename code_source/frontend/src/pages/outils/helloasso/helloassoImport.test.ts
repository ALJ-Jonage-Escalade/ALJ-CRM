import { describe, expect, it } from "vitest";
import type { Schemas } from "../../../lib/client";
import {
  attachedMemberId,
  attachLines,
  campaignOptions,
  canAttach,
  canReceive,
  changeLines,
  decisionsOf,
  incompleteRows,
  initialChoices,
  isCheckable,
  keepChoices,
  lastSyncText,
  memberHref,
  memberOptionLabel,
  needsIdentityChoice,
  refundText,
  resultSummary,
  reviewOptions,
  rowProblem,
  rowsOf,
  searchMembers,
  searchRows,
  selectedRows,
  statusIcon,
  statusLabel,
  type Choices,
  type MembershipMember,
  type MembershipPreview,
  type MembershipRow,
} from "./helloassoImport";

const row = (change: Partial<MembershipRow>): MembershipRow => ({
  item_id: 1,
  bucket: "new",
  reason: "",
  order_ref: "500",
  order_date: "2026-09-01T10:00:00",
  payment_date: "",
  refund_date: "",
  last_name: "WEASLEY",
  first_name: "Ginny",
  birth_date: "2013-08-11",
  licence: "123456",
  tarif_name: "Adulte",
  amount: 180,
  status: "Processed",
  candidates: [],
  can_create: true,
  changes: [],
  issues: [],
  corrections: [],
  values: {},
  ...change,
});

const member = (change: Partial<MembershipMember>): MembershipMember => ({
  user_id: 7,
  last_name: "WEASLEY",
  first_name: "Molly",
  birth_date: "1960-10-30",
  licence: "",
  membership: "manual",
  ...change,
});

const preview = (rows: MembershipRow[], members: MembershipMember[] = []): MembershipPreview => ({
  status: "success",
  season: "2026-2027",
  campaign: "adhesion-2026",
  blocked_reason: null,
  counts: { already_imported: 0, new: 0, renewal: 0, updated: 0, to_review: 0, blocked: 0 },
  rows,
  members,
});

const campaign = (change: Partial<Schemas["HelloAssoCampaign"]>): Schemas["HelloAssoCampaign"] => ({
  form_type: "Membership",
  slug: "adhesion",
  title: "Adhésion",
  private_title: "",
  state: "Public",
  activity_type: "",
  url: "",
  start_date: null,
  end_date: null,
  created_at: null,
  active: false,
  warning: null,
  ...change,
});

describe("helloassoImport", () => {
  it("lists the campaigns, the active one marked, and adds the active one HelloAsso did not list", () => {
    const campaigns = [campaign({ slug: "a", title: "A", active: true }), campaign({ slug: "b", title: "", state: "Draft" })];
    expect(campaignOptions({ active: { form_type: "Membership", slug: "a" }, configured: true, campaigns })).toEqual([
      { value: "a", label: "A (campagne active)" },
      { value: "b", label: "b (brouillon)" },
    ]);
    expect(campaignOptions({ active: { form_type: "Membership", slug: "z" }, configured: true, campaigns: [] })).toEqual([
      { value: "z", label: "z (campagne active)" },
    ]);
  });

  it("gives the rows of a bucket, the latest registrations first", () => {
    const rows = [
      row({ item_id: 1, order_date: "2026-09-01T10:00:00" }),
      row({ item_id: 2, order_date: "2026-09-03T10:00:00" }),
      row({ item_id: 3, bucket: "renewal" }),
      row({ item_id: 4, order_date: "" }),
    ];
    expect(rowsOf(preview(rows), "new").map((r) => r.item_id)).toEqual([2, 1, 4]);
  });

  it("searches rows by name in either order, licence, tarif or birth date, accents ignored", () => {
    const rows = [
      row({ item_id: 1 }),
      row({ item_id: 2, last_name: "LOVEGOOD", first_name: "Luna", birth_date: "2011-02-13", licence: "999", tarif_name: "Jeune" }),
    ];
    expect(searchRows(rows, "")).toHaveLength(2);
    expect(searchRows(rows, "ginny weasley").map((r) => r.item_id)).toEqual([1]);
    expect(searchRows(rows, "LÚNA").map((r) => r.item_id)).toEqual([2]);
    expect(searchRows(rows, "11/08/2013").map((r) => r.item_id)).toEqual([1]);
    expect(searchRows(rows, "jeune").map((r) => r.item_id)).toEqual([2]);
  });

  it("names the HelloAsso statuses and the refunds", () => {
    expect(statusLabel("Processed")).toBe("Payée");
    expect(statusLabel("Weird")).toBe("Weird");
    expect(statusIcon("Canceled")).toEqual({ icon: "🚫", tooltip: "Annulée (Canceled)" });
    expect(statusIcon("")).toEqual({ icon: "❔", tooltip: "Statut inconnu (vide)" });
    expect(refundText(row({ status: "Refunded", refund_date: "2026-10-14" }))).toBe("Remboursé le 14/10/2026");
    expect(refundText(row({ status: "Refunding", refund_date: "2026-10-14" }))).toBe("Remboursement en cours depuis le 14/10/2026");
  });

  it("tells which rows are checkable, need an identity choice or can be attached", () => {
    const review = row({ bucket: "to_review" });
    const conflict = row({ bucket: "to_review", changes: [{ field: "amount", crm: "150", before: "180", after: "200" }] });
    expect([row({}), row({ bucket: "updated" }), review, row({ bucket: "blocked" })].map(isCheckable)).toEqual([true, true, true, false]);
    expect([review, conflict, row({})].map(needsIdentityChoice)).toEqual([true, false, false]);
    expect([row({}), row({ bucket: "renewal" }), review, conflict, row({ bucket: "updated" })].map(canAttach)).toEqual([
      true,
      true,
      true,
      false,
      false,
    ]);
  });

  it("reads the member of an attach choice", () => {
    expect(attachedMemberId("attach:42")).toBe(42);
    expect(attachedMemberId("attach:")).toBeNull();
    expect(attachedMemberId("link:42")).toBeNull();
    expect(attachedMemberId("attach:4x")).toBeNull();
  });

  it("only gives a registration to a member without a HelloAsso or several manual memberships", () => {
    expect((["none", "manual", "several_manual", "helloasso"] as const).map((membership) => canReceive(member({ membership })))).toEqual([
      true,
      true,
      false,
      false,
    ]);
    expect(memberOptionLabel(member({ licence: "42" }))).toBe(
      "WEASLEY Molly (né(e) le 30/10/1960, licence 42) · reprend son adhésion manuelle",
    );
  });

  it("searches the members to attach, none before something is typed, at most 8", () => {
    const many = Array.from({ length: 10 }, (_, index) => member({ user_id: index, first_name: `Molly${index}` }));
    expect(searchMembers(many, " ")).toEqual([]);
    expect(searchMembers(many, "weasley")).toHaveLength(8);
    expect(searchMembers(many, "mölly3 weasley").map((m) => m.user_id)).toEqual([3]);
    expect(searchMembers(many, "weasley molly3").map((m) => m.user_id)).toEqual([3]);
  });

  describe("choices", () => {
    const rows = [
      row({ item_id: 1, bucket: "new" }),
      row({ item_id: 2, bucket: "to_review", last_name: "LOVEGOOD", first_name: "Luna", order_ref: "501" }),
      row({ item_id: 3, bucket: "to_review", changes: [{ field: "status", crm: "Processed", before: "Processed", after: "Refunded" }] }),
      row({ item_id: 4, bucket: "blocked" }),
    ];
    const members = [member({ user_id: 7 }), member({ user_id: 8, first_name: "Arthur", membership: "none" })];
    const data = preview(rows, members);

    it("starts with the writable rows checked and the rows to review unchecked", () => {
      expect(initialChoices(data)).toEqual({
        1: { checked: true, choice: "import", comment: "" },
        2: { checked: false, choice: "", comment: "" },
        3: { checked: false, choice: "import", comment: "" },
      });
    });

    it("asks for the member and the comment of an attach, and refuses a member chosen twice", () => {
      const choices: Choices = { ...initialChoices(data), 2: { checked: true, choice: "attach:", comment: "" } };
      expect(rowProblem(rows[1]!, data, choices)).toBe("Choisissez l'adhérent à rattacher.");
      choices[2] = { checked: true, choice: "attach:7", comment: " " };
      expect(rowProblem(rows[1]!, data, choices)).toBe("Commentaire requis pour LOVEGOOD Luna.");
      choices[1] = { checked: true, choice: "attach:7", comment: "même famille" };
      expect(rowProblem(rows[1]!, data, choices)).toBe("WEASLEY Molly est déjà choisi(e) pour une autre inscription de cet import.");
      expect(incompleteRows(data, choices).map((r) => r.item_id)).toEqual([1, 2]);
      expect(rowProblem(rows[0]!, data, { 1: { checked: false, choice: "attach:", comment: "" } })).toBeNull();
    });

    it("writes the checked complete rows and skips the others", () => {
      const choices: Choices = { ...initialChoices(data), 2: { checked: true, choice: "attach:8", comment: " cousin " } };
      expect(selectedRows(data, choices).map((r) => r.item_id)).toEqual([1, 2]);
      expect(decisionsOf(data, choices)).toEqual({
        1: { bucket: "new", choice: "import" },
        2: { bucket: "to_review", choice: "attach:8", comment: "cousin" },
        3: { bucket: "to_review", choice: "skip" },
      });
      expect(attachLines(data, choices)).toEqual([
        "🔗 LOVEGOOD Luna (commande 501) → WEASLEY Arthur, né(e) le 30/10/1960 · pas encore adhérent(e) cette saison",
      ]);
    });
  });

  it("describes the changes of a row, with the CRM value for a row to review", () => {
    const changes: MembershipRow["changes"] = [
      { field: "status", crm: "Processed", before: "Processed", after: "Refunded" },
      { field: "amount", crm: "150", before: "180", after: "200" },
    ];
    expect(changeLines(row({ bucket: "updated", changes }))).toEqual(["Statut : Payée → Remboursée", "Montant : 180 → 200"]);
    expect(changeLines(row({ bucket: "to_review", changes }))).toEqual([
      "Statut : CRM Payée · HelloAsso Remboursée (avant Payée)",
      "Montant : CRM 150 · HelloAsso 200 (avant 180)",
    ]);
  });

  it("offers the candidates, a new member when possible, and another member", () => {
    const candidate = { user_id: 9, last_name: "POTTER", first_name: "Lily", birth_date: "", licence: "" };
    expect(reviewOptions(row({ candidates: [candidate], can_create: false }))).toEqual([
      { value: "link:9", label: "Rattacher à POTTER Lily (né(e) le ?)" },
      { value: "attach:", label: "Rattacher à un autre adhérent…" },
    ]);
    expect(reviewOptions(row({})).map((option) => option.value)).toEqual(["create", "attach:"]);
  });

  it("links an imported member to their record of the season", () => {
    expect(memberHref({ user_id: 7, purchase_id: 12 }, "2026-2027")).toBe("/bureau/adherents?id=7&saison=2026-2027&achat=12");
    expect(memberHref({ user_id: 7 }, "2026-2027")).toBe("/bureau/adherents?id=7&saison=2026-2027");
  });

  it("sums up the import, singular and plural, attachments only when some", () => {
    const result: Schemas["MembershipImportResult"] = {
      status: "success",
      season: "2026-2027",
      history_id: "h",
      counts: { created: 1, renewed: 2, updated: 0, attached: 0, skipped: 1 },
      created: [],
      renewed: [],
      updated: [],
      attached: [],
    };
    expect(resultSummary(result)).toBe(
      "🎉 Import terminé (saison 2026-2027) : 1 adhérent créé, 2 renouvellements, 0 inscription mise à jour, 1 inscription non importée.",
    );
    expect(resultSummary({ ...result, counts: { ...result.counts, attached: 2 } })).toContain("2 inscriptions rattachées, ");
  });

  it("tells when the memberships were last synchronised", () => {
    expect(lastSyncText(null)).toBe("Aucune synchronisation des adhésions HelloAsso pour l'instant.");
    expect(lastSyncText({ at: "pas une date", author: "Albus", season: "2026-2027", campaign: "a" })).toBe(
      "Dernière synchro : pas une date, par Albus",
    );
    expect(lastSyncText({ at: "2026-10-24T14:05:00", author: "Albus", season: "2026-2027", campaign: "a" })).toMatch(
      /^Dernière synchro : 24\/10\/2026.*, par Albus$/,
    );
  });
});

describe("keepChoices", () => {
  it("keeps the admin's choices on the rows still in their section, and gives the moved rows their initial choice", () => {
    const before = preview([row({ item_id: 1 }), row({ item_id: 2, bucket: "to_review", candidates: [] })]);
    const after = preview([row({ item_id: 1 }), row({ item_id: 2, bucket: "renewal" })]);
    const choices: Choices = {
      1: { checked: false, choice: "import", comment: "" },
      2: { checked: true, choice: "create", comment: "" },
    };

    expect(keepChoices(before, after, choices)).toEqual({
      1: { checked: false, choice: "import", comment: "" },
      2: { checked: true, choice: "import", comment: "" },
    });
  });
});
