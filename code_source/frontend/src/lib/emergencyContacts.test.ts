import { describe, expect, it } from "vitest";
import { emergencyContactsOf } from "./emergencyContacts";

describe("emergencyContactsOf", () => {
  it("reads the list, in its order, however many contacts it holds", () => {
    const list = [
      { name: "A", phone: "01" },
      { name: "B", phone: "02" },
      { name: "C", phone: "03" },
    ];
    expect(emergencyContactsOf({ emergency_contacts: list })).toEqual(list);
  });

  it("prefers the list to the temporary flat fields, even empty", () => {
    expect(emergencyContactsOf({ emergency_contacts: [], emergency1_name: "Ancien", emergency1_phone: "01" })).toEqual([]);
  });

  it("reads a copy saved on the device before the list existed", () => {
    expect(emergencyContactsOf({ emergency1_name: "Paul", emergency1_phone: "01", emergency2_name: "", emergency2_phone: "02" })).toEqual([
      { name: "Paul", phone: "01" },
      { name: "", phone: "02" },
    ]);
  });

  it("leaves blank rows out", () => {
    expect(emergencyContactsOf({ emergency1_name: "", emergency1_phone: "", emergency2_name: null })).toEqual([]);
    expect(emergencyContactsOf({})).toEqual([]);
    expect(
      emergencyContactsOf({
        emergency_contacts: [
          { name: "", phone: "" },
          { name: "A", phone: "" },
        ],
      }),
    ).toEqual([{ name: "A", phone: "" }]);
  });
});
