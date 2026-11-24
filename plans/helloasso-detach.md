# Plan: Detach a membership from HelloAsso

> Source issue: https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/84 (follow-up of #70, phase 9 of
> `helloasso-membership-import.md`)

## Problem

A wrong match of the HelloAsso membership import (`attach:<id>`, `link:<id>`, a renewal or a create given to the wrong
person) cannot be undone: no route edits or deletes a membership, and `purchases.helloasso_item_id` keeps the item
"Déjà importé" forever.

## Decisions (grilled with the owner, 2026-11-24)

- **Where**: member record › « ⋯ Plus » › « 🔗 Détacher de HelloAsso ». Admin only. Shown only when the purchase
  of the record (`achat=` in the URL) has a `helloasso_item_id`. Not in the import preview (out of scope for now).
- **Scope**: any purchase linked to a HelloAsso item, whatever the import decision that wrote it (create, link,
  renewal, attach); only the purchase shown on the record; any season.
- **Effect**: the purchase is **deleted** with its insurance options (`ON DELETE CASCADE`), and its order when no other
  purchase uses it (one HelloAsso order can hold siblings). One SQLite transaction through the replicated repository
  path (deletes reach Firestore as tombstones).
- **No restore**: the values of a manual membership taken over by an attach are lost; the admin recreates it by hand
  if needed. The stats undercount until the item is attached again: accepted.
- **The member is never touched**: a member created by a wrong `create` stays (no member delete route); fields
  filled by a wrong `link:` stay (fixed with « Modifier »).
- **Next import**: the item is unknown again and is classified new / renewal / to review; the admin attaches it to the
  right member from Outils › Import HelloAsso.
- **Confirmation**: danger dialog naming the order, tarif, season and member, saying the membership is deleted, the
  record is not changed, and a licence already sent to the FFME is not cancelled there. **Reason required**.
- **Audit**: one document in the import history (`helloasso_membership_imports`), `kind: "detach"`, with `at`,
  `author`, `season`, `item_id`, `order_ref`, `user_id`, `member` (name), `purchase_id`, `tarif`, `amount`, `reason`.
  `latest()` is not changed: "last sync" may show the detach (accepted, nobody relies on it).
- **After**: the record closes (`id` / `achat` removed from the URL), the list reloads, a toast says what was deleted
  and where to attach the registration again.
- **Offline**: the menu item is visible but disabled (« Connexion requise »).

## Architecture

- **Route**: `POST /api/members/purchases/{purchase_id}/detach-helloasso`, body `{reason}` →
  `{status, message, item_id, order_ref, season}`. Admin through the existing `/api/members` write branch of
  `required_role`; listed in `tests/test_route_inventory.py`. Errors: 404 unknown purchase, 400 blank reason or purchase
  without HelloAsso item.
- **Service**: `services/members/helloasso_detach.py`: checks, delete, history entry; raises `domain.errors`.
- **Repository**: `MembershipImportRepository.detach(purchase_id)` in `infrastructure/sqlite/membership_import.py`
  returns what was deleted (member, season, order, item, tarif, amount), `None` when the purchase is unknown.
- **History**: `MembershipImportHistory.record_detach(entry)` with a `DetachHistoryEntry` TypedDict.
- **Member view**: the member list rows expose `helloasso_item_id` (nullable); OpenAPI and `api-schema.ts` regenerated.
- **Frontend**: `detachHelloAsso(purchaseId, reason)` in the members service; the record's « Plus » menu emits
  `detach`; the page opens the dialog (reason textarea), calls the API, closes the record, reloads, toasts.
- **Version**: bump `APP_VERSION` and `VERSION`.

## Behaviours tested

Backend (through the HTTP routes, temporary SQLite + in-memory Firestore, HelloAsso mocked):
1. Detaching an attached membership deletes the purchase and its order; the next preview classifies the registration
   as new again
2. The detach leaves a `kind: "detach"` history entry with author, item, order, member, season and reason
3. A blank reason is refused, nothing deleted
4. A purchase without HelloAsso item is refused; an unknown purchase is 404
5. An order shared with another purchase is kept
6. The member list exposes `helloasso_item_id`

Frontend (Vitest, AdherentsPage):
7. The « Plus » menu offers « Détacher de HelloAsso » to an admin on a HelloAsso membership only
8. Confirming with a reason posts it, closes the record, reloads the list, toasts; offline the item is disabled

## Acceptance criteria

- [x] An admin detaches a HelloAsso membership from the member record, with a required reason
- [x] The purchase, its options and its order left empty are deleted; the member is unchanged
- [x] The next import preview no longer shows the item as already imported
- [x] The detach is recorded in the import history
- [x] Coaches and readonly users neither see nor can call the action; offline it is disabled
