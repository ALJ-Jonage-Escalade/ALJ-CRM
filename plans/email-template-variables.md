# Plan: Readable e-mail template variables and template types

> Source PRD: https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/28

## Architectural decisions

Durable decisions that apply across all phases:

- **Single reference**: the variable registry lives on the server, in the domain layer. Each variable has a key (stored), a
  French label (displayed), the template kinds it belongs to, a demo value, and its behaviour when empty; legacy aliases
  are listed there too. The existing replacement function stays as a thin adapter (member + optional competition context →
  values) and every send path (bulk/competition dispatch, member e-mail, attestation) goes through it.
- **Variables**:
  | Label | Key | Kinds |
  |---|---|---|
  | Prénom | `first_name` | all |
  | Nom | `last_name` | all |
  | N° de licence | `num_licence` | all |
  | Tarif | `tarif` | all |
  | Saison | `season` | all |
  | Montant de l'adhésion | `amount` | adherent, attestation |
  | Nom de la compétition | `name_competition` | competition |
  | N° de la compétition | `no_competition` | competition |
  | Date de la compétition | `date_competition` | competition |
  | Montant de la compétition | `montant_competition` | competition |
  | Lien WhatsApp | `whatsapp_link` | competition |
- **Aliases** (accepted when sending, normalised to the key on save, never offered): `Prénom`, `Nom`, `nom_competition`,
  the `whatapp_Id` / `whatsapp_id` / … variants (→ `whatsapp_link`), `bloc_whatsapp` (expands to "Voici le lien du groupe
  WhatsApp dédié à cette compétition : <link>").
- **Token syntax**: `{…}` with no `<`, `>`, `"` or line break inside. Lenient matching folds case, accents and spaces with
  the existing name-normalisation helpers.
- **Rendering rules**: a known variable with no value → empty string; a line holding an empty Lien WhatsApp is removed;
  amounts use the existing French euro formatter (`15`, `15,50`, no "€"); member values HTML-escaped when the body is HTML.
- **Schema**: `email_templates` gains `kind` (`adherent` | `attestation` | `competition`) and `is_default` (boolean).
  Stored subject/body keep internal keys (`{first_name}`); labels are display-only.
- **Lazy migration**: no production write up front. A missing `kind` is inferred on read from today's name rules
  ("compétition" → competition, "attestation"/"échéance" → attestation, else adherent); tokens are normalised on the next
  save.
- **Default template**: at most one `is_default` per kind, enforced by the save route in the same write; changing kind
  drops the flag; with no flagged template, screens fall back to the name rules.
- **Routes**:
  - `GET /api/email-templates/variables` (admin): per variable key, label, kinds, demo value, aliases.
  - `POST /api/email-templates`: 400 (`api.responses.error()`) on an unknown or wrong-kind token; accepts `kind`, `is_default`.
  - `GET /api/email-templates`: each template carries `kind`, `is_default` and a "needs fixing" flag.
- **API contract**: variable keys are a `Literal` in a Pydantic schema, so they reach `api-schema.ts`; the frontend value
  builders are typed `Record<VariableKey, …>`, so an unhandled key fails `typecheck`.
- **Frontend**: one variables module (TS mirror of the registry: labels ↔ keys, validation, rendering, member and
  competition value builders) and one shared template textarea component (textarea + picker filtered by kind +
  bold/italic/underline/link toolbar + inline errors). Text is shown in labels and converted to keys before saving or sending.
- **Golden fixture**: one JSON file (texts, values, expected outputs) checked by pytest and Vitest.
- **Roles**: unchanged (template writes admin, variables route admin, coaches send through `/api/send-email`).
- **Versioning**: bump `APP_VERSION` and `VERSION` together in each phase that ships.

---

## Phase 1: Server variable registry behind every send

**User stories**: 21, 28, 29, 30, 31, 32 (server side), 33, 34

### What to build

The server variable registry (keys, labels, kinds, demo values, empty behaviour, aliases) with rendering, and the existing
replacement function turned into a thin adapter over it. Every send path (bulk/competition dispatch, member e-mail,
attestation) renders through it. Members stop receiving raw tokens: empty values vanish, `{amount}` is filled from the
membership, legacy tokens (`{nom_competition}`, `{bloc_whatsapp}`, `{whatapp_Id}`…) keep working, the WhatsApp line
disappears without a link, and "WhatsApp" is spelled correctly. No UI or schema change.

### Acceptance criteria

- [ ] Each variable renders its value; each alias renders like its canonical key
- [ ] An empty known variable (tarif, season, competition fields) renders as an empty string, never as the raw token
- [ ] A line holding an empty Lien WhatsApp is removed; `{bloc_whatsapp}` expands to the WhatsApp sentence
- [ ] `{amount}` and `{montant_competition}` use the French euro formatter (`15`, `15,50`, no "€")
- [ ] Member values are HTML-escaped when the body is HTML; braces inside HTML tags or links are left alone
- [ ] Send-path tests: no raw `{…}` left for the default templates, `{amount}` and `{nom_competition}` included
- [ ] An e-mail sent in the dev stack (Mailpit) shows every variable filled

---

## Phase 2: Previews identical to sending

**User stories**: 9, 10, 32, 35, 36

### What to build

The variable keys exposed as a `Literal` in the API contract and the admin route `GET /api/email-templates/variables`.
A frontend variables module mirrors the registry's rendering and replaces the three preview renderers (Communications
editor, member record, competition e-mail), with member and competition value builders typed on the variable keys. A shared
golden fixture is checked by pytest and Vitest. The editor still shows keys; only the previews change.

### Acceptance criteria

- [ ] `GET /api/email-templates/variables` returns key, label, kinds, demo value and aliases; admin only; in the route inventory
- [ ] OpenAPI file and TS schema regenerated; removing a key from a value builder fails `npm run typecheck`
- [ ] The golden fixture passes in both pytest and Vitest (same output text)
- [ ] Previews are case-sensitive like the server, fill every variable (including `{no_competition}`, `{name_competition}`,
      WhatsApp) with demo values, and show amounts as `15,50`
- [ ] The three old preview renderers are gone

---

## Phase 3: French labels and picker on the Communications page

**User stories**: 1, 2, 4, 5, 6, 7, 20, 37

### What to build

Label ↔ key conversion with lenient matching, in the registry and its TS mirror, plus validation of unknown tokens. The
shared template textarea component (picker, toolbar, inline errors) on the Communications page for subject and body: the
template is loaded in labels, legacy tokens shown with their current label, and converted to keys on save. Save is
blocked while an unknown token remains, in the UI and by the save route (400). Without kinds yet, the picker offers every
variable.

### Acceptance criteria

- [ ] Templates load with French labels; legacy tokens appear as their current label
- [ ] Clicking a picker entry inserts its label at the cursor
- [ ] `{prénom}`, `{PRENOM}`, `{ Prénom }` are accepted and rewritten to `{Prénom}`; the API receives `{first_name}`
- [ ] An unknown token blocks save with a message naming it and listing the valid labels
- [ ] The save route rejects an unknown token with a 400, whatever the client sent
- [ ] Label → key → label round-trip is lossless (golden fixture extended)

---

## Phase 4: Template kinds

**User stories**: 3, 8, 11, 12, 17, 18, 19

### What to build

The `kind` column on templates, inferred from the name rules when missing. The Communications page gets a kind selector
and a list grouped by kind. The picker shows only the variables of the template's kind. Validation rejects a variable of
another kind, also when the kind changes. The template list flags templates holding invalid or legacy tokens and the UI shows
"⚠️ à corriger" on them.

### Acceptance criteria

- [ ] A template without `kind` reads with the kind inferred from its name; nothing is written until it is saved
- [ ] `kind` is saved and synced to Firestore with the template
- [ ] The picker lists only variables of the selected kind
- [ ] A competition variable in an Adhérent template blocks save (UI and 400 from the route), also after changing the kind
- [ ] The list is grouped by kind; templates with invalid or legacy tokens show "⚠️ à corriger"
- [ ] OpenAPI / TS schema regenerated for `kind` and the flag

---

## Phase 5: Default template per kind

**User stories**: 13, 14, 15, 16

### What to build

The `is_default` column and a "Modèle par défaut pour ce type" checkbox. Saving a template as default unmarks the previous
default of the same kind in the same write. Renaming keeps the flag; changing the kind drops it, and the user is told so.

### Acceptance criteria

- [ ] At most one default per kind after any save
- [ ] Renaming a default template keeps it default
- [ ] Changing the kind drops the default flag and the UI shows a notice before saving
- [ ] The list shows which template is the default of each kind
- [ ] OpenAPI / TS schema regenerated for `is_default`

---

## Phase 6: Send screens by kind

**User stories**: 22, 23, 24, 25, 26, 27

### What to build

The member e-mail, attestation e-mail and competition e-mail screens use the shared template textarea for subject and body,
in labels, converted to keys before sending. Each screen offers only templates of its kind and preselects the default,
falling back to today's name rules. Free-text e-mails get the variables of their context (member variables from a member
record, competition variables from a competition). The name-based template guessing is removed from these screens.

### Acceptance criteria

- [ ] Member record e-mail: only Adhérent templates, default preselected, member variables in the picker
- [ ] Attestation e-mail: only Attestation templates, default preselected
- [ ] Competition e-mail: only Compétition templates, default preselected, competition variables in the picker (free text included)
- [ ] With no default flagged, each screen falls back to the name rules
- [ ] Subject and body show labels; the send request carries keys; the sent e-mail has no raw token
- [ ] Offline/error path of each screen unchanged (template list unavailable does not block a free-text e-mail)
