# Base des adhérents dans Firestore (v2.4.0)

Depuis le 8 octobre 2026, la base principale (ex-`database.db` partagée sur Google Drive)
est stockée dans Firestore, projet `smart-amplifier-510811-n6`.

## Organisation

| Table SQLite | Collection Firestore | ID du document |
|---|---|---|
| seasons, users, orders, purchases, purchase_options, planning, email_templates | `crm_<table>` | ID SQLite |
| geocache (clé texte) | `crm_<table>` | `h` + SHA-1 de la clé |

Chaque document contient les colonnes de la ligne, plus :
`_modified_at` (horodatage serveur), `_modified_by` (poste), `_deleted` (ligne supprimée).

Les collections `adherents` et `planning` (annuaire lu par la PWA et le webhook) sont des
**projections** recalculées automatiquement après chaque modification d'adhérents
(au plus toutes les 3 minutes, et à la fermeture de l'application).

## Fonctionnement de l'application de bureau

- `database.db` est un **cache** : reconstruit depuis Firestore au premier lancement
  (l'ancien fichier est sauvegardé dans `data/backups/database_avant_firestore_*.db`),
  puis mis à jour de façon incrémentale.
- Des déclencheurs SQLite notent chaque ligne modifiée ; elles sont envoyées toutes les
  15 s, champ par champ, avec contrôle de version : deux postes qui modifient des champs
  différents d'un même adhérent ne s'écrasent pas.
- Les modifications des autres postes sont reçues toutes les 2 minutes, et à chaque
  « Télécharger » / synchronisation HelloAsso.
- Hors connexion : l'application travaille sur la copie locale ; les modifications
  partent au retour du réseau (pied de page : « ⏳ N modification(s) à envoyer »).

## Annuaire web (application Vue, `frontend/src/pages/AnnuairePage.vue`, URL `/index`)

- Lit `GET /api/seasons` et `GET /api/members?season=` (une saison à la fois). La liste
  est calculée sur le serveur (`domain/member_view.py`) depuis son cache SQLite des
  collections `crm_*` ; le navigateur ne lit plus Firestore.
- Réservé aux coachs/admins (rôle vérifié par l'API). Connexion Google commune avec
  `/competitions` : le bouton « Se connecter » passe par `/competitions?login=1`
  (URI de redirection OAuth déjà autorisée) puis revient sur l'annuaire
  (`sessionStorage.alj_after_login`).
- Actualisation toutes les 20 s quand la page est visible (`useSyncedResource`, ETag/304).
- Lecture hors ligne : la dernière liste reçue est gardée dans IndexedDB (`alj-offline`,
  `frontend/src/lib/store.ts`), sans les données de santé ni de paiement, et affichée avec
  sa date quand le réseau manque ; effacée à la déconnexion, sur un 401/403, pour un autre
  compte et au bout de 30 jours.

Code : `src/infrastructure/cloud_database.py`.

## Cloud Run

Le serveur construit son cache au premier appel d'une route de données, le rafraîchit
si la dernière réception date de plus de 30 s et envoie ses écritures (planning,
e-mails, géocodage) juste après la requête.

## Migration, vérification

```
ALJ_FIRESTORE_ACCESS_TOKEN=$(gcloud auth print-access-token) \
  python src/migrate_sqlite_to_firestore.py chemin/database.db --dry-run | --apply | --verify
```

`--verify` reconstruit un cache depuis Firestore et le compare à la source, table par
table puis via `list_flat_member_rows` pour chaque saison.

Migration du 08/10/2026 : 1 991 documents, vérification identique pour 2025-2026
(264 adhésions) et 2026-2027 (287).

## Sauvegardes

Deux niveaux, décrits et vérifiés par `code_source/scripts/setup_firestore_backups.sh`
(`--check` : rapport en lecture seule, code de sortie 1 s'il manque quelque chose ;
`--apply` : crée ce qui manque, après confirmation, sans rien modifier ni supprimer) :

1. Restauration à un instant donné (PITR, 7 jours, à la minute) et protection contre la
   suppression de la base.
2. Sauvegardes Firestore gérées : quotidienne conservée 14 jours, hebdomadaire (dimanche)
   conservée 14 semaines.

Coût : ~2 000 documents (quelques Mo), donc ≈ 0 €/mois. Limite assumée : ces sauvegardes
restent dans le projet Google Cloud et disparaîtraient avec lui.

Copie de la base source avant migration :
`gs://smart-amplifier-510811-n6-sauvegardes-alj/database/`.

### Restaurer

Une restauration crée une **nouvelle** base ; l'application lit toujours `(default)`
(`infrastructure/firestore/client.py`). On restaure donc dans une base temporaire, on la
contrôle, puis on la recopie dans `(default)` par export/import.

```
P=smart-amplifier-510811-n6

# a) Depuis une sauvegarde (liste : gcloud firestore backups list)
gcloud firestore databases restore --project=$P --destination-database=restore-test \
  --source-backup=projects/$P/locations/europe-west1/backups/<ID>

# b) Ou depuis PITR (instant des 7 derniers jours, en UTC)
gcloud firestore databases clone --project=$P --destination-database=restore-test \
  --source-database="projects/$P/databases/(default)" --snapshot-time=2026-10-25T08:00:00Z

# Recopier restore-test dans (default), puis supprimer la base temporaire
gcloud firestore export gs://smart-amplifier-510811-n6-sauvegardes-alj/restauration \
  --project=$P --database=restore-test
gcloud firestore import gs://smart-amplifier-510811-n6-sauvegardes-alj/restauration/<DOSSIER> \
  --project=$P --database="(default)"
gcloud firestore databases delete --project=$P --database=restore-test
```

- L'import écrase les documents de même identifiant mais **ne supprime pas** ceux créés
  depuis la sauvegarde : pour un retour exact, vider d'abord les collections `crm_*` concernées.
- Après l'import, déployer une nouvelle révision Cloud Run pour reconstruire le cache SQLite
  `database.db` depuis Firestore.
- Ne jamais importer un export de production dans l'émulateur local (données personnelles).

## Retour arrière

Paramètres → « Base principale » = `drive` : l'application revient au partage du fichier
`database.db` par Google Drive (les modifications faites dans Firestore depuis la
bascule n'y figurent pas).

## Droits (firestore.rules)

Aucun accès client (`allow read, write: if false` sur tous les documents) : les pages
web passent par l'API, qui vérifie les rôles (`api_auth.py`). L'application de bureau
(jeton OAuth du club) et Cloud Run (compte de service) passent par IAM, auquel les
règles ne s'appliquent pas. Ordre de déploiement : README, section Cloud Run.
