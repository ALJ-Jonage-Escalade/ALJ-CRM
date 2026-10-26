# ALJ-CRM

Gestion des adhésions de la section Escalade de l'Amicale Laïque de Jonage : application web (FastAPI + PWA)
sur Google Cloud Run, données dans Firestore. L'ancien client lourd Windows a été retiré ; les fonctions qui
n'existent pas encore sur le web sont listées dans
[documentations/desktop_features_missing_in_web.md](documentations/desktop_features_missing_in_web.md).
Architecture détaillée : [documentations/ARCHITECTURE.md](documentations/ARCHITECTURE.md).
Les écrans web sont une application Vue 3 (`code_source/frontend/`), la même sur téléphone et sur ordinateur :
[plans/vue-responsive-frontend.md](plans/vue-responsive-frontend.md).

## Lancer l'application en mode dev local

Tout tourne sur la machine : émulateur Firebase (projet fictif `demo-alj`), données fictives,
e-mails capturés par Mailpit. **Aucun accès aux données ni aux services de production.**

### Prérequis (une fois)

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0   # + Docker
# uv : https://docs.astral.sh/uv/getting-started/installation/  (Windows : winget install astral-sh.uv)
cd code_source
uv sync --group web          # crée .venv/ aux versions exactes de uv.lock (profil web + outils de dev)
# Node (application Vue) : version de code_source/frontend/.nvmrc, par exemple avec nvm
cd frontend && nvm install && npm ci   # node_modules/ aux versions exactes de package-lock.json
```

Toutes les commandes Python se lancent ensuite avec `uv run <commande>` (inutile d'activer le venv).

Sans uv, `pip install -r requirements-docker.txt -r requirements-dev.txt` reste possible : ces fichiers sont générés
à partir de `uv.lock`.

### Gérer les dépendances

`pyproject.toml` (+ `uv.lock`) fait foi. Les `requirements*.txt` sont **générés** : ne pas les éditer à la main
(installations pip, tests e2e ; le CI vérifie qu'ils sont à jour).

```bash
cd code_source
# 1. modifier les dépendances dans pyproject.toml (ou `uv add <paquet>` / `uv add --group dev <paquet>`)
uv lock                                     # met à jour uv.lock
uv run python dev/export_requirements.py    # régénère requirements*.txt
```

### Démarrage

```bash
cd code_source
docker compose -f dev/docker-compose.yml up -d    # émulateur Firebase + Mailpit
set -a && source dev/dev.env && set +a
uv run python dev/seed/seed_emulator.py            # (ré)initialise les données fictives
uv run dev/run_server.sh                           # serveur FastAPI avec rechargement auto
cd frontend && npm run dev                         # application Vue (autre terminal), rechargement à chaud
```

L'application Vue répond sur http://localhost:5173/bureau/ et renvoie au serveur FastAPI (port 8080) l'API
et les fichiers de la PWA. Sans `npm run dev`, http://localhost:8080/bureau/ sert la dernière compilation
(`npm run build`), ou explique comment la lancer.

Arrêt : `Ctrl+C` pour le serveur, `docker compose -f dev/docker-compose.yml down` pour les conteneurs
(les données de l'émulateur sont conservées dans `dev/.emulator-data/`).

### URL utiles

| URL | Contenu |
|---|---|
| http://localhost:5173/bureau/ | Portail bureau, application Vue (`npm run dev`) |
| http://localhost:8080/bureau/ | Portail bureau servi par FastAPI (application Vue compilée) |
| http://localhost:5173/competitions | Compétitions, application Vue (téléphone et ordinateur, lisible hors ligne) ; retour de la connexion Google |
| http://localhost:5173/index | Annuaire des adhérents, application Vue (téléphone et ordinateur, lisible hors ligne) |
| http://localhost:8080/health | État du serveur |
| http://localhost:8080/docs | Documentation de l'API (Swagger) |
| http://localhost:4000 | Interface de l'émulateur Firebase (Firestore, Auth) |
| http://localhost:8025 | Mailpit : e-mails envoyés par l'application |

### Comptes de connexion

« Se connecter » ouvre le sélecteur de comptes de l'émulateur :

| Compte | Rôle |
|---|---|
| `albus.dumbledore@alj-escalade.fr` | admin |
| `severus.snape@hogwarts.example` | coach |
| `argus.filch@hogwarts.example` | lecture seule |

### À savoir

- Un bandeau orange « DEV » en bas de page confirme le branchement sur l'émulateur.
- `dev/run_server.sh` refuse de démarrer si un `.env` du dépôt réactive Gmail ou un SMTP externe.
- HelloAsso (`/api/dashboard`, synchro) appelle l'API réelle : en erreur sans identifiants.
- Plus de détails : [code_source/dev/README.md](code_source/dev/README.md).

### Scripts Windows

Les scripts se lancent d'un double-clic, depuis n'importe quel dossier : chacun se place lui-même
dans le bon répertoire de travail.

| Script | Rôle |
|---|---|
| `scripts/lancer_site_web.bat` | Serveur web local → http://127.0.0.1:8000/bureau/ ; compile d'abord l'interface (`npm run build`, nécessite [Node.js](https://nodejs.org/)) |
| `scripts/deploy_cloud_run.bat` | Déploiement en production (appelle `code_source/scripts/deploy_cloud_run.bat`) |
| `scripts/backup_projet.ps1` | Sauvegarde ZIP du projet (`.\scripts\backup_projet.ps1 [-Destination E:\]`) |
| `code_source/scripts/lancer_site_web.bat` | Serveur web local |
| `code_source/scripts/deploy_cloud_run.sh` / `.bat` | Déploiement Cloud Run (voir plus bas) |

## Tests

```bash
cd code_source
uv run pytest tests                               # après uv sync --group web (comme la CI)
uv run ruff check src tests
uv run mypy                                       # fichiers listés dans [tool.mypy] de pyproject.toml
cd frontend && npm run lint && npm run format:check && npm run typecheck && npm test   # application Vue (ESLint, Prettier, vue-tsc, Vitest)
```

Contrat de l'API : les types TypeScript de l'application Vue sont générés à partir des modèles Pydantic des routes.
Après avoir modifié un modèle de réponse :

```bash
cd code_source
uv run python dev/export_openapi.py               # met à jour frontend/openapi.json
cd frontend && npm run gen:api                    # régénère src/lib/api-schema.ts (vérifié par la CI)
```

## Déployer sur Cloud Run

Depuis Google Cloud Shell ou un poste avec le Google Cloud SDK (le script envoie toujours `code_source/`,
quel que soit le dossier courant) :

```bash
cd code_source
./scripts/deploy_cloud_run.sh                     # production : la nouvelle version reçoit 100 % du trafic
./scripts/deploy_cloud_run.sh --test              # version de test : 0 % du trafic, URL dédiée
./scripts/deploy_cloud_run.sh --rollback          # retour à la révision précédant celle en ligne
./scripts/deploy_cloud_run.sh --rollback <REV>    # retour à une révision précise
./scripts/deploy_cloud_run.sh --cleanup           # supprime l'URL de test (la révision est conservée)
```

Chaque déploiement crée une **révision** Cloud Run immuable ; le script affiche la révision en ligne,
demande confirmation, puis donne l'URL de l'application à la fin.

### Tester avant la mise en production

1. `./scripts/deploy_cloud_run.sh --test` : la révision est publiée sur une URL du type
   `https://test---alj-escalade-api-….run.app`, sans recevoir de trafic.
2. Vérifier sur cette URL : `/health`, connexion, pages modifiées.
3. Promouvoir sans reconstruire avec la commande `gcloud run services update-traffic … --to-tags test=100`
   affichée par le script (ou relancer un déploiement de production).
4. `./scripts/deploy_cloud_run.sh --cleanup` une fois les tests terminés : l'URL de test, branchée sur les
   données de production, cesse de répondre. Une révision sans trafic ne coûte rien (0 instance au
   repos) ; seules les images Docker s'accumulent dans Artifact Registry (`cloud-run-source-deploy`).

### Revenir en arrière

`./scripts/deploy_cloud_run.sh --rollback` bascule tout le trafic sur une ancienne révision, sans reconstruction,
en quelques secondes. Le script liste les dernières révisions : vérifier que la cible n'est pas une
version de test jamais promue. Après un déploiement en production, la commande de retour exacte est
affichée. Le prochain déploiement en production renvoie le trafic sur la nouvelle révision.

### À savoir

- La version de test utilise **les données Firestore et les secrets de production** : toute action
  (envoi d'e-mails, modification d'adhérents) y est réelle.
- Un rollback ne restaure que le code, jamais les données.
- Connexion Google et renouvellement (`Erreur 400 : redirect_uri_mismatch`) : la connexion Google passe par
  le client OAuth Web `796572126711-npcue84…` (projet `smart-amplifier-510811-n6`). Dans la console
  Google Cloud > API et services > Identifiants > ce client OAuth, ajouter :
  - **Origines JavaScript autorisées** :
    - Production : `https://alj-escalade-api-bdxfydatoa-ew.a.run.app`
    - Test : `https://test---alj-escalade-api-bdxfydatoa-ew.a.run.app`
  - **URI de redirection autorisés** :
    - `https://alj-escalade-api-bdxfydatoa-ew.a.run.app/competitions`
    - `https://alj-escalade-api-bdxfydatoa-ew.a.run.app/api/auth/google/callback`
    - `https://test---alj-escalade-api-bdxfydatoa-ew.a.run.app/competitions`
    - `https://test---alj-escalade-api-bdxfydatoa-ew.a.run.app/api/auth/google/callback`

  La prise en compte par Google peut prendre quelques minutes.
- Les webhooks HelloAsso arrivent toujours sur l'URL principale, donc sur la révision de production.
- `code_source/firestore/firestore.rules` n'est **pas** déployé par ce script
  (`cd code_source/firestore && firebase deploy --only firestore:rules`, à côté de `firebase.json`) :
  les règles s'appliquent immédiatement à toute la production. Historique et retour arrière dans la
  console Firebase > Firestore > Rules.
- Depuis la version web v23, `firestore.rules` **refuse tout client** (les pages passent par l'API).
  Ne le déployer qu'**au moins une semaine après** la mise en production de la v23, et après avoir
  vérifié dans la console GCP que les requêtes Firestore évaluées par les règles sont tombées à ~0 ;
  sinon les PWA encore en v22 ou moins perdent l'accès. Retour arrière :
  `git checkout <commit précédent> -- code_source/firestore/firestore.rules`, puis
  `cd code_source/firestore && firebase deploy --only firestore:rules`.
- `scripts/deploy_cloud_run.bat` (Windows) ne fait qu'un déploiement en production, sans `--test` ni `--rollback`.
