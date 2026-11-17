/* A member's emergency contacts, as a list. Copies saved on a device before the list existed hold the two flat fields
   instead (IndexedDB, plans/emergency-contacts.md, D9): they keep working offline. */

export interface EmergencyContactRow {
  name: string;
  phone: string;
}

/** What a member, a directory entry or a competitor entry holds about their contacts. */
export interface EmergencyContactSource {
  emergency_contacts?: readonly { name?: string; phone?: string }[] | null;
  emergency1_name?: string | null;
  emergency1_phone?: string | null;
  emergency2_name?: string | null;
  emergency2_phone?: string | null;
}

/** The contacts in order, the first one being the main one; blank rows left out. */
export function emergencyContactsOf(source: EmergencyContactSource): EmergencyContactRow[] {
  const rows = source.emergency_contacts ?? [
    { name: source.emergency1_name ?? "", phone: source.emergency1_phone ?? "" },
    { name: source.emergency2_name ?? "", phone: source.emergency2_phone ?? "" },
  ];
  return rows.map((row) => ({ name: row.name ?? "", phone: row.phone ?? "" })).filter((row) => row.name || row.phone);
}
