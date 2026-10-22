/** Roles as answered by GET /api/me: the server (api_auth.py) is the only judge, pages only display them. */
export type Role = "admin" | "coach" | "readonly" | null;

const ROLE_LABEL = {
  admin: "🛡️ Administrateur",
  coach: "🏃 Coach",
  readonly: "👁️ Lecture seule",
} as const;

export function roleLabel(role: Role): string {
  return role ? ROLE_LABEL[role] : "⛔ Non autorisé";
}

/** The office portal is for coaches and administrators. */
export function isStaff(role: Role): boolean {
  return role === "admin" || role === "coach";
}
