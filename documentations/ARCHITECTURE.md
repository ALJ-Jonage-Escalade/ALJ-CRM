# ALJ-CRM — Architecture & onboarding

> Gestion des adhésions de la section Escalade de l'Amicale Laïque de Jonage (ALJ).
> Ce document décrit l'état réel du code. Il a été rédigé par lecture du code et des docs existantes ; les points
> marqués **(à vérifier)** n'ont pas été confirmés en exécutant l'application.
> Le client lourd Windows (PySide6) a été retiré : les fonctions qui n'existent pas encore sur le web sont listées
> dans `desktop_features_missing_in_web.md`.

---

## 1. En une minute

Le dépôt contient **une seule base de code Python** (`../code_source`) qui produit **une application web** :

| | Application web |
|---|---|
| Techno | FastAPI + HTML/JS statique (sans build) servi par FastAPI |
| Où ça tourne | Google Cloud Run (`europe-west1`, 0→2 instances) |
| Point d'entrée | `src/server.py` (`uvicorn server:app`) |
| Données | Uniquement via l'API (`/api/*`) ; le serveur lit Firestore (compétitions) et un cache SQLite éphémère (adhérents). Le navigateur n'utilise Firebase que pour la connexion. |
| Utilisateurs | Coachs et admins (PWA smartphone + portail bureau) |

**Firestore** (projet GCP `smart-amplifier-510811-n6`) est la source de vérité. Cloud Run lance `server.py` dans
Docker (auth Firebase obligatoire).

```
    HelloAsso ──webhook──┐
    HelloAsso ◄──API v5──┤
                         ▼
          ┌───────────────────────────┐     ┌──────────────────────────┐
          │ CLOUD RUN — server.py     │     │ NAVIGATEUR               │
          │ FastAPI + API + HTML      │     │ web/ (PWA + portail      │
          │ WeasyPrint (PDF)          │◄────┤ bureau), Firebase Auth   │
          │ cache SQLite éphémère     │ API │ (connexion seulement)    │
          └─────────────┬─────────────┘     └──────────────────────────┘
                        │ REST v1 (metadata server)
                        ▼
                         ┌─────────────────────────────────────┐
                         │ FIRESTORE  crm_* / competitions /   │
                         │ coaches / adherents / planning …    │
                         └─────────────────────────────────────┘
          Gmail API (OAuth2 club)  ·  Google Drive (copie de sauvegarde)  ·  Nominatim (géocodage)
          Cloud Scheduler (07:00) → POST /api/competitions/cron/fetch-results (résultats MyCompet)
```

---

## 2. Arborescence

```
ALJ-CRM/                         ← racine du dépôt
├── code_source/                 ← TOUT le code (la racine ne contient que des doublons/raccourcis, voir §9)
│   ├── src/
│   │   ├── server.py            ← entrée WEB/API : assemble l'app FastAPI (middlewares, routeurs de api/), aucune route
│   │   ├── paths.py             ← CODE_ROOT / ROOT_DIR / DATA_ROOT (à utiliser, ne jamais recalculer)
│   │   ├── domain/              ← Python pur : members/, competitions/, attestation/ + constants, utils, validators
│   │   ├── api/                 ← routeurs FastAPI, un fichier par domaine, rangés par thème (voir §4)
│   │   ├── services/            ← cas d'usage, rangés comme api/ : competitions/, members/ (les autres thèmes
│   │   │                          gardent encore leur logique dans le routeur)
│   │   ├── infrastructure/      ← accès externes, un dossier par système : security/ (auth API, secrets),
│   │   │                          sqlite/ (+ migrations/), firestore/, google/, mail/, helloasso/, mycompet/, qrcodes/
│   │   ├── exports/             ← générateurs de fichiers : membership_excel (CSV FFME, Excel adhérents),
│   │   │                          presence_sheets, planning_excel, spreadsheet_safety
│   ├── web/
│   │   ├── index.html           ← PWA « annuaire » (smartphone)
│   │   ├── competitions.html    ← PWA « compétitions » (smartphone, 2700 lignes)
│   │   ├── sw.js, manifest.webmanifest
│   │   ├── bureau/              ← portail ordinateur, pages pas encore migrées vers l'application Vue (frontend/) : competitions
│   │   └── shared/              ← alj-firebase.js (init Firebase unique + émulateur dev), alj-core.js (login/apiFetch), alj-shell.js (menu),
│   │                              alj-sync.js / alj-members-sync.js (lecture de l'API), alj-vue.js (redirection bureau/mobile), alj.css
│   ├── tests/                   ← tests pytest/unittest, rangés comme le code testé : domain/, exports/, infrastructure/, services/, api/, web/ ; modules racine de src/ à la racine
│   ├── dev/                     ← mode dev local : émulateur Firebase (Docker), dev.env, run_server.sh, seed/ (données fictives)
│   ├── docs/                    ← docs d'architecture/plan (partiellement obsolètes, voir §8)
│   ├── doc/template/            ← modèles HTML/Excel (attestation, liste de présence)
│   ├── Dockerfile, requirements-docker.txt, deploy_cloud_run.{sh,bat}, firestore.rules, firebase.json
│   ├── VERSION                  ← 2.5.8 (source de vérité, doit == APP_VERSION dans domain/constants.py)
│   └── GEMINI.md                ← doc historique la plus détaillée (voir §8 pour ses limites)
├── .github/workflows/           ← tests (ruff, mypy, pytest, e2e) + déploiement Cloud Run sur main
└── GEMINI.md, *.bat…            ← doublons/raccourcis de la racine (deploy_cloud_run.bat, lancer_site_web.bat)
```

### Couches (code_source/src)

- **`domain/`** — pur Python, sans I/O.
  Rangé en `members/` (modèles, liste web, `age_rules`, `planning_groups`), `competitions/` (modèles,
  `matching` HelloAsso), `attestation/` (`document.build_attestation()`, HTML → PDF WeasyPrint) ;
  `constants`, `utils.apply_template_variables`, `validators` restent à la racine.
- **`infrastructure/`** — adaptateurs, un sous-dossier par système externe. Les plus structurants :
  - `sqlite/schema_v2.py` : DDL SQLite, normalisations, vue de compatibilité `v_adherents_legacy` (**source unique**, recréée à chaque démarrage).
  - `sqlite/connection.py` (`SqliteDatabase` : chemin, connexion, schéma, sauvegarde) et un repository par domaine :
    `members.py` (`get_members()` typé recommandé, `load_direct_data()` legacy), `seasons.py`, `planning.py`,
    `email_templates.py`, `geocache.py`, `ffme_import.py`.
  - `firestore/cloud_database.py` : réplication SQLite ⇄ Firestore (collections `crm_<table>`, triggers `_fs_*`, flush toutes les 15 s, pull toutes les 2 min, merge champ par champ) ; façade `CloudDatabase` s'appuyant sur `firestore/cloud_sync/` : `common` (constantes, conversions), `rest_store` (REST Firestore), `cache` (SQLite, déclencheurs), `sync` (pull / flush / fusion), `bootstrap` (reconstruction du cache, import initial).
  - `firestore/client.py` : client REST Firestore (sans gRPC) ; `firestore/competition_repository.py` : compétitions (façade `CompetitionFirestoreRepository` composant les mixins de `firestore/competitions/` : adhérents, épreuves, participants, miroir HelloAsso, coachs) ;
    `firestore/app_settings.py` : réglages applicatifs (collection `app_settings`, seul emplacement).
  - `security/api_auth.py` : middleware Firebase (rôles `readonly < coach < admin`). Seul juge des droits : `firestore.rules` refuse tout accès client.
  - `mail/` (envoi, campagnes, corps HTML), `helloasso/` (API v5, webhook), `security/secret_store.py`, `google/drive.py` (OAuth Google, Drive).

---

## 3. Modèle de données

Schéma v2 (SQLite, répliqué en Firestore sous `crm_<table>`) :

`users` (identité stable inter-saisons) → `orders` (commande HelloAsso) → `purchases` (une inscription par saison)
→ `purchase_options` (assurances) ; + `seasons`, `planning` (créneaux/groupes avec bornes de naissance),
`geocache`, `email_templates`, `app_settings`.

Autres collections Firestore : `competitions/{id}` (participants **embarqués**), `coaches`, `adherents` et
`planning` (projections pour PWA/webhook, recalculées après modification), `app_settings`, `helloasso_items`.

Particularités à connaître :
- Chaque document `crm_*` porte `_modified_at`, `_modified_by`, `_deleted` (tombstone).
- Les IDs de compétitions sont `str(Date.now())` ; les anciens IDs aléatoires sont normalisés à la lecture.
- Le web reconstruit `v_adherents_legacy` **en JavaScript** (`web/shared/alj-members.js`) à partir de `crm_*` : toute évolution du schéma/vue SQL doit être répercutée des deux côtés.
- Détails : `base_firestore.md`.

---

## 4. Backend — routes (`src/api/`)

`server.py` ne contient aucune route : il vérifie l'environnement, installe les middlewares (cache SQLite,
auth, garde du serveur local, en-têtes de sécurité) puis inclut les routeurs de `src/api/<thème>/<domaine>.py`.

| Thème (`api/…`) | Fichiers | Routes |
|---|---|---|
| `web/` | `pages`, `pwa`, `health` | `/`, `/index`, `/competitions`, `/bureau`, `/bureau/{page}` (liste blanche), `/annuaire` et `/static-web/*` (`mount_static`) · `/sw.js`, `/manifest.webmanifest`, `/runtime-config.js`, `/api/web-version` · `/health` |
| `members/` | `members`, `seasons`, `dashboard` | `/api/members` (+ `/competitors`, `/update`, `/create`, `/add`) · `/api/seasons`, `/api/season-tarifs` · `/api/dashboard` |
| `competitions/` | `competitions`, `participants`, `coaches`, `members`, `helloasso_items`, `results`, `payments` | `/api/competitions/*`, `/api/coaches`, `/api/competition-members`, `/api/helloasso/items` · résultats MyCompet (`/api/competitions/cron/fetch-results`, `/{id}/fetch-results`, `/api/settings/competitions-results`) · `/{id}/check-all-paid` |
| `communications/` | `email`, `whatsapp`, `attestations` | `/api/email-templates` (GET/POST/DELETE), `/api/preview-email`, `/api/email-status`, `/api/send-email` · `/api/whatsapp-template` · `/api/attestations/preview`, `/send` (PDF en mémoire, admin) |
| `activities/` | `planning`, `presence` | `/api/planning` (GET/POST, `/item`, `/export`) · `/api/presence/config`, `/export` |
| `reports/` | `map`, `pivot` | `/map`, `/pivot` (pages HTML générées côté serveur, chargées en `iframe srcdoc`) |
| `ffme/` | `ffme` | `/api/ffme/stats`, `/export` (CSV), `/preview`, `/import` |
| `integrations/` | `helloasso`, `google_auth`, `cloud_db` | `/webhooks/helloasso` (GET/POST), `/api/helloasso/sync` · `/api/auth/google/*` · `/api/cloud-db/status`, `/sync` |

- **Cache SQLite** : les routeurs `competitions`, `participants`, `coaches`, `members` (compétitions) et `helloasso_items`
  ne lisent que Firestore et sautent le rafraîchissement du cache (`FIRESTORE_ONLY_PATHS`). Une route qui lit ou écrit le
  cache va dans un autre routeur, même sous `/api/competitions` (`results`, `payments`).
- **URL appelées de l'extérieur, à ne pas changer** : Cloud Scheduler (job `batch-resultats-competitions`,
  `POST /api/competitions/cron/fetch-results` chaque jour à 07h00 — à déclarer avant `/{id}/fetch-results`), webhook
  HelloAsso, retours OAuth Google (console Google Cloud), `/health` (déploiement). `tests/test_route_inventory.py`
  fige la liste complète des routes.

**Auth** : `ALJ_API_AUTH=required` (Docker) ou présence de `K_SERVICE` (Cloud Run) → jeton Firebase obligatoire, fail-closed.
Pages statiques publiques (`PUBLIC_PATHS` / `PUBLIC_PREFIXES`), données protégées. Les listes d'e-mails admin/coach sont **codées en dur** dans `api_auth.py`, recopiées pour l'affichage seulement dans `alj-core.js`, `competitions.html` et `../index.html` (un test vérifie la cohérence — modifier les quatre). `firestore.rules` ne contient plus de rôle : il refuse tout client.

---

## 5. Front web

- **Aucun framework ni build** : HTML + JS ES modules + CSS, Firebase Auth (connexion seulement), `fetch` via `apiFetch` (`alj-core.js`, ajoute le jeton Bearer).
- **Toutes les données passent par l'API** (plan `plan_api_only_front.md`) : aucune page ne charge le SDK Firestore. Les écrans se mettent à jour par interrogation (`alj-sync.js`, `alj-members-sync.js` : toutes les 20 s quand la page est visible, ETag/304). Hors ligne, seule la PWA compétitions affiche une copie en lecture seule (`alj-store.js`, IndexedDB `alj-offline` : épreuves, coachs et, pour les coachs, contacts d'urgence des compétiteurs via `GET /api/members/competitors` ; 30 jours au plus, effacée à la déconnexion ou à la perte du rôle) ; l'annuaire nécessite le réseau. Hors ligne, seule la case « Participe » d'un compétiteur inscrit peut changer : la modification est gardée dans la file `outbox` du même magasin et envoyée au retour du réseau avec le `updated_at` du compétiteur vu par le téléphone (`unchanged_since`) ; le serveur la refuse (409 `changed`) si le compétiteur a changé entre-temps, ou si la compétition est archivée (phase 5b du plan). `alj-firebase.js` efface au démarrage l'ancien cache Firestore (IndexedDB) des téléphones.
- **Deux « vues »** : PWA smartphone (`/competitions`, `/index`) et portail bureau (`/bureau/*`). `alj-vue.js` redirige automatiquement les écrans ≥ 1024 px vers `/bureau/` (`?vue=mobile` pour forcer la PWA).
- **Un seul numéro de version web** à garder synchronisé : `<meta alj-web-version>`, `<title>`, badge, et `CACHE_NAME` de `sw.js` (le test `test_mobile_pwa` le vérifie). Chaque déploiement visible = version web +1 (actuellement v23).
- Rôles : coach/readonly = lecture ; admin = envoi e-mail/attestation, écritures.
- Plan et décisions du portail : `plan_pages_web_bureau.md`.

---

## 6. Fonctions de l'ancien client lourd à porter sur le web

Le client lourd Windows a été retiré. La liste des fonctions qui n'existent pas (ou pas entièrement) sur le web,
avec le code backend conservé et le code supprimé (récupérable dans l'historique git), est dans
`desktop_features_missing_in_web.md`.

### Obstacles techniques récurrents

1. **Logique métier dans des fichiers legacy** : `exports/membership_excel.py` (exports FFME), certaines méthodes de `infrastructure/sqlite/ffme_import.py` sans appelant depuis le retrait du client lourd (`merge_autonomes_data`, `merge_ffme_licensees`). À exposer en routes FastAPI avant de construire l'écran web.
2. **Système de fichiers** : Cloud Run est éphémère → génération **en mémoire** puis téléchargement (comme les attestations), jamais de persistance locale.
3. **Cache SQLite côté serveur** : reconstruit depuis Firestore au premier appel de données (`CloudDatabase.ensure_fresh`, 30 s) et flush après chaque écriture. Une route d'écriture doit passer par les repositories de `infrastructure/sqlite/` pour être répliquée.
4. **Durée des requêtes** : timeout Cloud Run 300 s, mémoire 1 GiB (Pandas/WeasyPrint) ; les traitements lourds (géocodage Nominatim à 1,5 s/adresse) doivent rester en tâche de fond.
5. **Données personnelles/RGPD** (santé, urgences, mineurs) : ne jamais committer de BDD/exports ; golden master FFME non versionné (`tests/fixtures/`).

### Démarche recommandée pour chaque fonction à porter

1. Reprendre la logique (historique git du client lourd ou méthode conservée) dans `domain/` (pur) ou `infrastructure/`.
2. Exposer une route FastAPI (rôle explicite : `admin` pour toute écriture/envoi).
3. Écrire le test (pytest sur la route, ou test de fonction pure).
4. Ajouter l'écran dans `web/bureau/` en réutilisant `alj-core.js`, `alj-shell.js`, `alj.css`.
5. Incrémenter la version web (meta/title/badge/`sw.js`) et déployer.
6. Mettre à jour `desktop_features_missing_in_web.md`.

---

## 7. Démarrer en local

### 7.1 Installation (une fois)

```bash
# Debian/Ubuntu : module venv + libs Pango pour WeasyPrint (cf. Dockerfile) ; Docker pour l'émulateur
sudo apt install libpango-1.0-0 libpangoft2-1.0-0

cd code_source
uv sync --group web          # .venv/ (ignoré par git) : profil « web » + outils de dev + Faker
source .venv/bin/activate
```

Les dépendances sont déclarées dans `pyproject.toml` et verrouillées dans `uv.lock` (versions exactes, identiques en
CI, en dev et dans l'image Docker). Les `requirements*.txt` en sont des exports générés
(`python dev/export_requirements.py`) pour les installations avec pip (tests e2e).

La version de Python est définie dans `../code_source/.python-version` (version complète, ex. `3.14.8`), lue par
la CI (`setup-python`) et uv. Seul le `FROM python:<version>-slim` du `Dockerfile` la répète : un test
(`tests/test_cloud_run_lot4.py`) vérifie que les deux concordent. Pour changer de version, modifier ces **deux
fichiers** (vérifier d'abord que les roues existent : `pip download --only-binary=:all: --python-version X.Y …`).

### 7.2 Mode dev sur l'émulateur Firebase (recommandé)

Front + API + Firestore entièrement locaux, sur le projet fictif **`demo-alj`** de l'émulateur Firebase
(Auth + Firestore), avec des **données fictives** (univers Harry Potter). Mode d'emploi : `../code_source/dev/README.md`.

```bash
cd code_source
docker compose -f dev/docker-compose.yml up -d     # émulateur Firebase (UI :4000) + Mailpit (UI :8025)
set -a && source dev/dev.env && set +a
python dev/seed/seed_emulator.py                    # réinitialise + données fictives + comptes de connexion
dev/run_server.sh                                   # http://localhost:8080/bureau/
```

Connexion par le sélecteur de comptes de l'émulateur : `albus.dumbledore@alj-escalade.fr` (admin),
`severus.snape@hogwarts.example` (coach), `argus.filch@hogwarts.example` (lecture seule).

Fonctionnement :

- **Source unique côté serveur** : `src/infrastructure/runtime_env.py`. `ALJ_ENV=dev` redirige l'URL Firestore, le jeton
  (`owner`, admin de l'émulateur) et le projet (`demo-alj`) de `cloud_database.RestStore` et `FirestoreClient` ;
  active le rafraîchissement du cache comme sur Cloud Run. Sans `ALJ_ENV`, rien ne change (production).
- **E-mails** : aucun code spécifique. `dev.env` dirige le SMTP de l'application (`SMTP_HOST=localhost`,
  `SMTP_PORT=1025`, variables `GMAIL_*` vides) vers **Mailpit** (conteneur de `dev/docker-compose.yml`), qui capture
  tout sans relayer : http://localhost:8025. `dev/check_env.py` (lancé par `run_server.sh`) vérifie la configuration
  effective, `.env` du dépôt compris (le `.env` racine est chargé en `override=True`), et refuse de démarrer si
  l'API Gmail est active ou si le SMTP n'est pas local.
- **Navigateur** : `GET /runtime-config.js` (jamais mis en cache par `sw.js`) définit `window.ALJ_RUNTIME` ;
  `web/shared/alj-firebase.js` est la **seule** initialisation Firebase de toutes les pages (configuration du projet
  comprise) et branche l'émulateur en dev, avec un bandeau « DEV ». La détection ne repose pas sur `localhost` :
  un serveur local hors mode dev (`lancer_site_web.bat`, §7.3) sert aussi ces pages et doit rester en production.
- **Garde-fous** : un projet `demo-*` n'existe pas chez Google (aucun accès réel possible, même mal configuré) ;
  `runtime_env.validate()` refuse le mode dev sur Cloud Run (`K_SERVICE`) ou sans variables d'émulateur ;
  le seed refuse de s'exécuter hors émulateur ; les tests retirent les variables dev (`tests/conftest.py`).
- L'émulateur applique le vrai `firestore.rules` et conserve ses données dans `dev/.emulator-data/` (ignoré par git).
- Limites : `/api/dashboard` et la synchro HelloAsso interrogent l'API HelloAsso réelle (lecture) ; sans identifiants,
  ces écrans sont en erreur.

### 7.3 Serveur seul, sans émulateur

Pour un simple contrôle de l'API (aucune page connectée utilisable : la connexion Google réelle refuse `localhost`) :

```bash
ALJ_API_AUTH=off MEMBER_BACKEND=drive ALJ_DATA_DIR=./data-dev \
  uvicorn server:app --app-dir src --host 127.0.0.1 --port 8080 --reload
# Docker (identique à la prod) :
docker build -t alj . && docker run -p 8080:8080 -e ALJ_API_AUTH=off -e MEMBER_BACKEND=drive alj
```

- `ALJ_API_AUTH=off` : désactive le contrôle du jeton Firebase côté API (serveur local uniquement ; `api_auth.local_request_error` bloque alors les requêtes inter-sites).
- `ALJ_DATA_DIR` : dossier du cache SQLite `database.db` (défaut : `<racine du dépôt>/data`), créé vide au premier accès.
- `MEMBER_BACKEND` : `firestore` par défaut. **Hors mode dev**, `firestore` pousse les écritures du serveur local vers le
  **Firestore de production** (`CloudDatabase.after_write`) ; `drive` = SQLite local seul.
- ⚠️ Hors mode dev, le serveur local lit et écrit **le Firestore de production** pour les compétitions, coachs et
  éléments HelloAsso (les pages passent par l'API), quel que soit `MEMBER_BACKEND`.

**Configuration / secrets** : `../code_source/.env` (non versionné) ; sur Cloud Run, variables d'environnement / Secret Manager.
Clés principales : `HELLOASSO_CLIENT_ID/SECRET/ORG_SLUG`, `CAMPAIGN_SLUG`, `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN/USER_EMAIL`, `SMTP_*`, `GOOGLE_DRIVE_*`, `MEMBER_BACKEND` (`firestore`|`drive`), `ALJ_DATA_DIR`, `ALJ_API_AUTH`. Ne jamais afficher ni committer ces valeurs.

**Tests** (depuis `../code_source`) :

```bash
uv sync --group web && uv run pytest tests
```
La CI (Ubuntu) lance `ruff check src tests`, `mypy` (fichiers listés dans `[tool.mypy] files`) et `pytest tests` ; tous sont bloquants. `test_ffme_golden_master` nécessite un fichier de référence local non versionné.

**Déploiement web** : `../code_source/scripts/deploy_cloud_run.sh` (ou `.bat`) → `gcloud run deploy alj-escalade-api --source . --memory 1Gi --min-instances 0 --max-instances 2 --session-affinity --timeout 300 --allow-unauthenticated` (l'auth est applicative). Règles Firestore : `firebase deploy --only firestore:rules` (`firebase.json`), manuel et **séparé** du déploiement de l'application : refus total des clients, à déployer au moins une semaine après la version web qui ne lit plus Firestore (ordre et retour arrière : plan `plan_api_only_front.md`, S1). Guide : `guide_deploiement_cloud_run_helloasso.md`.

**Tâche planifiée** : la tâche Cloud Scheduler `batch-resultats-competitions` (07:00, Europe/Paris) appelle `POST /api/competitions/cron/fetch-results`. Elle a été créée à la main dans GCP (hors dépôt).

**Plus de release desktop** : ne plus pousser de tag `v*`. Les anciens postes installés interrogent encore `releases/latest` ; une nouvelle release sans le client lourd casserait leur mise à jour automatique.

---

## 8. Pièges & dette connue

- **Documentation partiellement périmée** : `../GEMINI.md` (racine et `code_source/`) décrit encore Tkinter, un fonctionnement 100 % Windows/Excel/Drive et des chemins de l'ancien poste. `architecture_actuelle.md` et `plan_migration.md` datent de la migration Tkinter→PySide6. `plan_architecture_cloud_mobile.md` annonce `APP_VERSION 2.3.0`, `512Mi`. `pyproject.toml` dit `2.0.5`. **Faire confiance au code et à `VERSION`, puis `base_firestore.md` et `plan_pages_web_bureau.md` (les plus récents).**
- `../GEMINI.md` impose une convention utile : scripts de diagnostic jetables dans `scripts_temporaires/` (ignoré par git), jamais à la racine.
- **Duplication du front** : `competitions.html` (2700 lignes) et `../index.html` dupliquent historiquement auth/style ; le portail `bureau/` utilise `shared/`. Ne pas dupliquer davantage.
- **Admins codés en dur** (`api_auth.py` + copies d'affichage en JS) : à terme, passer par les custom claims Firebase.
- **Exports FFME** : CSV strict (`;`, dates `jj/mm/aaaa`) ; le golden master doit rester vert ou être renouvelé avec accord du club.
- **Sauvegardes** : API backup SQLite (jamais de copie brute avec WAL), PITR Firestore 7 j, export quotidien 14 j, retour arrière via `MEMBER_BACKEND=drive`.
- Le dépôt contient aussi `../.agents`, `.idea/`, `.jolli/` (outillage local).

---

## 9. Pour commencer concrètement

1. Lire dans l'ordre : ce fichier → `base_firestore.md` → `plan_pages_web_bureau.md` → `src/server.py` puis `src/api/` (§4) → `web/shared/alj-core.js` → `web/bureau/adherents.html` (page de référence).
2. Lancer le serveur en local et ouvrir `/bureau/` (§7) ; lancer les tests web/API.
3. Choisir une fonction manquante dans `desktop_features_missing_in_web.md` (§6).
4. Décider des questions ouvertes avec le club : envoi groupé (quotas Gmail, anti-doublon), droit d'écriture sur le web, hébergement des secrets (Secret Manager), sort de `database.db` Drive (retour arrière).
