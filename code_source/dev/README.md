# Environnement de développement local

Front + API + Firestore en local, sur l'**émulateur Firebase** (Auth + Firestore) du projet
fictif `demo-alj`, avec des **données fictives** (univers Harry Potter). Aucun accès possible
aux données de production : un projet `demo-*` n'existe pas chez Google et le serveur refuse
le mode dev sur Cloud Run. Détails et architecture : `documentations/ARCHITECTURE.md` §7.

## Démarrage

Prérequis : Docker et [uv](https://docs.astral.sh/uv/) (`uv sync --group web` crée `.venv/` depuis `uv.lock`).

```bash
cd code_source
docker compose -f dev/docker-compose.yml up -d     # émulateur (UI :4000) + Mailpit (UI :8025)
set -a && source dev/dev.env && set +a
uv run python dev/seed/seed_emulator.py             # réinitialise + données fictives
uv run dev/run_server.sh                            # API, fichiers PWA (port 8080)
cd frontend && npm ci && npm run dev                # application Vue : http://localhost:5173/bureau/
```

Vite (port 5173) sert l'application Vue avec rechargement à chaud et relaie au serveur FastAPI (8080) l'API,
`/runtime-config.js`, le manifeste et les anciennes adresses (`vite.config.ts`). Le serveur FastAPI
seul sert la dernière compilation (`npm run build` → `frontend/dist/`, service worker `dist/sw.js` compris ; il
n'est enregistré que par la compilation, jamais par `npm run dev`).

Connexion : le bouton « Se connecter » ouvre le sélecteur de comptes de l'émulateur.

| Compte | Rôle |
|---|---|
| `albus.dumbledore@alj-escalade.fr` | admin |
| `severus.snape@hogwarts.example` | coach |
| `argus.filch@hogwarts.example` | lecture seule |

Les rôles sont dans la liste des accès de l'émulateur (collection `access_roles`, écrite par `seed_emulator.py`), comme
en production. Des données d'émulateur créées avant cette liste (« Accès réservé » pour Albus) se réparent sans tout
réinitialiser : `uv run python dev/seed/seed_emulator.py --access-only` (comptes de test et leurs rôles, le reste est
gardé). En mode dev, le serveur relit la liste à chaque appel : un seed ou une modification dans l'interface de
l'émulateur s'applique tout de suite. « Add new account » crée un compte sans rôle : il est refusé, et sa demande apparaît sur
Administration › Accès, où Albus peut lui donner un rôle. L'administrateur initial (`BOOTSTRAP_ADMIN_EMAIL`) n'est
jamais ajouté en mode dev.

## Bon à savoir

- **Bandeau orange « DEV »** en bas de page : la page est branchée sur l'émulateur.
- **E-mails** : l'application envoie par son SMTP habituel, dirigé par `dev.env` vers **Mailpit**, qui les garde
  sans jamais les relayer. Lecture (HTML, pièces jointes PDF) : http://localhost:8025, ou
  `docker compose -f dev/docker-compose.yml logs -f mailpit`. Messages perdus au redémarrage du conteneur.
- **Garde-fou** : `run_server.sh` lance `check_env.py`, qui lit la configuration effective (y compris les `.env`
  du dépôt, prioritaires sur `dev.env`) et refuse de démarrer si l'API Gmail est active ou si le SMTP n'est pas local.
- **Persistance** : l'émulateur exporte ses données dans `dev/.emulator-data/` à l'arrêt
  (`docker compose -f dev/docker-compose.yml down`) et les recharge au démarrage.
  Relancer le seed repart de zéro (et vide le cache `data-dev/` du serveur).
- **Règles** : l'émulateur applique le vrai `firestore.rules` (monté en lecture seule) : refus de tout client.
  Le serveur passe par le jeton administrateur de l'émulateur (`owner`), qui joue le rôle d'IAM.
- **HelloAsso** : la synchro et l'import des adhésions HelloAsso appellent l'API HelloAsso réelle (lecture)
  si des identifiants sont configurés ; sans eux, ces écrans sont en erreur. En mode dev uniquement,
  `HELLOASSO_API_BASE_URL` / `HELLOASSO_OAUTH_URL` les redirigent vers un faux HelloAsso local
  (`e2e/fakes/helloasso_fake.py`, utilisé par les tests e2e) ; `check_env.py` refuse toute autre adresse.
  Pour la page **Paramètres › Campagne HelloAsso**, charger quelques formulaires datés dans le faux
  (`uvicorn helloasso_fake:app --app-dir e2e/fakes --port 8095`, il filtre sur `states` / `formTypes` comme l'API ; comme elle, la liste n'a pas `activityType` / `activityTypeId`, lus sur le détail `/public` de chaque formulaire) :
  ```bash
  curl -X PUT localhost:8095/_e2e/state -H 'Content-Type: application/json' -d '{"items": [], "forms": [
    {"formSlug": "adhesion-2026", "formType": "Membership", "state": "Public", "title": "Adhésion 2026-2027",
     "meta": {"createdAt": "2026-07-01T10:00:00+02:00"}},
    {"formSlug": "competitions-2026", "formType": "Event", "state": "Private", "title": "Compétitions 2026-2027",
     "activityType": "Compétition", "activityTypeId": 3,
     "startDate": "2026-09-15T00:00:00+02:00", "endDate": "2027-06-30T23:59:00+02:00"},
    {"formSlug": "competitions-2025", "formType": "Event", "state": "Disabled", "title": "Compétitions 2025-2026",
     "activityType": "Compétition", "activityTypeId": 3,
     "startDate": "2025-09-15T00:00:00+02:00", "endDate": "2026-06-30T23:59:00+02:00"},
    {"formSlug": "soiree-club-2026", "formType": "Event", "state": "Public", "title": "Soirée du club",
     "activityType": "Fête", "activityTypeId": 1, "startDate": "2026-12-12T19:00:00+01:00"}]}'
  ```
- **Résultats MyCompet** : le batch des résultats (bouton de la page Paramètres) et « Trouver les résultats » lisent
  le vrai site MyCompet et les archives FFME. Pour essayer sans eux, un faux MyCompet local
  (`e2e/fakes/mycompet_fake.py`, port `8096`) sert des pages anonymisées
  (`tests/support/mycompet/results_template.html`) avec les participants du seed :
  ```bash
  uv run uvicorn mycompet_fake:app --app-dir e2e/fakes --port 8096      # autre terminal
  export MYCOMPET_BASE_URL=http://localhost:8096 FFME_ARCHIVES_URL=http://localhost:8096/archives
  uv run python dev/seed/mycompet_state.py                              # publie les résultats des épreuves passées
  uv run dev/run_server.sh                                              # mêmes variables exportées
  ```
  Le seed contient une épreuve terminée il y a 5 jours (dans la fenêtre de 30 jours du batch) et une il y a 35 jours
  (hors fenêtre, sauf « Lancer la détection maintenant », qui force). Variables ignorées hors mode dev.
  Le gabarit se régénère depuis une vraie page enregistrée **hors du dépôt** (`scripts_temporaires/`, données
  personnelles) : `uv run python dev/make_mycompet_fixture.py <page.html>` remplace chaque grimpeur par une identité
  inventée ; `tests/infrastructure/mycompet/test_fake_pages.py` le vérifie. Relire le fichier avant de le committer.
- **Service worker** : en cas de page figée après un changement, « Mettre à jour » sur le badge
  de version ou désenregistrer le SW (DevTools → Application).

## Tests e2e (Playwright)

Tests navigateur de bout en bout dans `code_source/e2e/`, sur leur **propre pile jetable** (émulateur + Mailpit,
`e2e/docker-compose.yml`), que la suite démarre puis supprime elle-même : la pile de dev ci-dessus et ses données
ne sont jamais touchées, et chaque exécution part d'un émulateur neuf. Ils sont lancés par la CI (job `e2e` de
`.github/workflows/tests.yml`, Ubuntu) à chaque PR et push sur `main`.

```bash
cd code_source
(cd frontend && npm ci && npm run build)             # le serveur de test sert l'application Vue compilée
pip install -r requirements-docker.txt -r requirements-e2e.txt
python -m playwright install --with-deps chromium    # WSL/Linux : bibliothèques système (sudo)
python -m pytest -c e2e/pytest.ini e2e -m smoke      # rapide ; sans -m : toute la suite
```

- **En parallèle** : 2 processus (pytest-xdist, `-n 2` dans `e2e/pytest.ini`), environ 1 min pour toute la suite.
  La pile, le seed, le faux HelloAsso et le serveur sont démarrés une seule fois, par le processus principal
  (`e2e/helpers/session.py`), puis partagés par les processus. En ajouter n'accélère pas la suite (un seul serveur et
  un seul émulateur pour tous). `-n 0` : un seul processus (pour déboguer avec `--headed`).
- Tests qui modifient un état lu par d'autres tests (faux HelloAsso, créneaux du planning) : même
  `xdist_group` (`pytestmark`), exécutés l'un après l'autre sur un même processus. Mailpit n'est vidé qu'une fois par
  exécution : chercher ses e-mails par destinataire **et** sujet (`unique_name`).
- Ports de la pile e2e : Firestore `18081`, Auth `19099`, Mailpit `18025` (SMTP `11025`) ; serveur de test
  `8090` (`E2E_PORT`), faux HelloAsso `8095`, faux MyCompet `8096`. La pile de dev (`8081`, `9099`, `8025`) et `run_server.sh` (`8080`)
  peuvent rester lancés. Docker est requis.
- `E2E_KEEP_STACK=1` garde la pile e2e après l'exécution (itérations rapides, ou lecture des journaux :
  `docker compose -f e2e/docker-compose.yml logs`) ; la suite la réensemence à chaque exécution. La supprimer ensuite
  (`docker compose -f e2e/docker-compose.yml down`) : la mémoire de l'émulateur grossit à chaque exécution.
- **Sans installer les bibliothèques système de Chromium** (WSL sans sudo) : navigateur servi par l'image
  officielle Playwright (même version que `requirements-e2e.txt`), réseau de l'hôte pour joindre `localhost` :
  ```bash
  docker run -d --name alj-e2e-browser --network host --init --ipc=host --user pwuser \
    mcr.microsoft.com/playwright:v1.63.0-noble \
    /bin/sh -c "cd /home/pwuser && npx -y playwright@1.63.0 run-server --port 3000 --host 127.0.0.1"
  E2E_PLAYWRIGHT_WS=ws://127.0.0.1:3000/ python -m pytest -c e2e/pytest.ini e2e
  ```
- Connexion sans passer par le sélecteur de comptes : `login_as(page, "admin" | "coach" | "readonly")`
  (`e2e/helpers/auth.py`). E-mails : fixture `mailpit` (`e2e/helpers/mailpit.py`). Données de test : fixture
  `test_data` (`e2e/helpers/data.py`), qui passe par le dépôt de l'application ; chaque test crée ses propres
  compétitions sous un nom unique.
  Les pages mettent à jour l'affichage avant l'écriture Firestore : une lecture après une action dans la page passe
  par `eventually(check)` (même fichier), qui réessaie ses `assert` jusqu'à 5 s.
- Bugs connus (`xfail`) : délais de 2 s au lieu de 5 s / 30 s (fixture `known_bug_timeouts`) ; pas de `timeout=`
  explicite sur l'étape qui échoue.
- HelloAsso : fixture `fake_helloasso` (faux serveur sur le port `8095`, `e2e/helpers/helloasso.py`) ; chaque test
  y charge ses propres paiements (`fake_helloasso.set([item(...)])`), le webhook est appelé avec
  `HELLOASSO_WEBHOOK_TOKEN`.
- MyCompet : fixture `fake_mycompet` (faux serveur sur le port `8096`, `e2e/helpers/mycompet.py`) ; chaque test y
  publie ses pages de résultats (`fake_mycompet.set([...])`), groupe xdist `mycompet`.
- Bugs connus : tests marqués `xfail(strict=True)` avec la référence du bug (ex. A6 de
  `documentations/plan_api_only_front.md`). Ils échouent (XPASS) dès que le bug est corrigé : retirer alors le marqueur.
- Déboguer : `-n 0 --headed --slowmo 300`, ou `--tracing retain-on-failure` puis
  `python -m playwright show-trace e2e-results/<test>/trace.zip`. Journaux de la pile, du serveur et du seed :
  `test-results/stack.log`, `test-results/server.log` (`e2e-results/` avec `--output e2e-results`, comme la CI).
- En CI, en cas d'échec : les tests en échec sont relancés avec traces (`--last-failed --tracing on`, la tâche reste en échec même s'ils passent), artefact `e2e-results` (captures, journaux serveur et Docker ; traces dans `rerun/` ; pas de vidéo : l'enregistrement de chaque test surcharge le runner).

## Fichiers

| Fichier | Rôle |
|---|---|
| `docker-compose.yml`, `emulator/Dockerfile` | émulateur Firebase (`firebase-tools` épinglé, Node 22 + Java 21) et Mailpit |
| `dev.env` | variables du mode dev (`ALJ_ENV=dev`, hôtes de l'émulateur…) — aucun secret |
| `run_server.sh` | charge `dev.env`, vérifie l'émulateur et Mailpit, lance `check_env.py` puis uvicorn `--reload` |
| `check_env.py` | refuse le démarrage si un e-mail pouvait partir réellement ou si l'émulateur manque |
| `seed/seed_emulator.py`, `seed/hp_names.py` | données fictives (Faker, graine fixe) |
| `../src/infrastructure/runtime_env.py` | source unique prod/dev côté serveur |
| `../frontend/src/lib/firebase.ts` | initialisation Firebase unique côté navigateur |
