# ==============================================================================
# Dockerfile — ALJ Escalade Manager API & PWA (Google Cloud Run)
# Architecture Cloud & Mobile (Coût 0 €/mois sur Google Cloud Free Tier)
# ==============================================================================

# ------------------------------------------------------------------------------
# Étape 1 — Application web Vue (frontend/) : compilée ici, jamais envoyée toute faite
# (dist/ est exclu de l'envoi). Même version de Node que frontend/.nvmrc et la CI.
# ------------------------------------------------------------------------------
FROM node:24.22.1-slim AS frontend

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
# La version affichée par l'application vient de VERSION (vite.config.ts)
COPY VERSION /build/VERSION
RUN npm run build

# ------------------------------------------------------------------------------
# Étape 2 — API FastAPI + pages web
# ------------------------------------------------------------------------------
FROM python:3.14.8-slim

# Configuration de l'environnement Python et conteneur
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    ALJ_DATA_DIR=/app/data \
    ALJ_API_AUTH=required \
    PYTHONPATH=/app/src:/app

WORKDIR /app

# 1. Dépendances système pour WeasyPrint (génération des attestations PDF sur Cloud Run)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libfontconfig1 \
    libjpeg62-turbo \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# 2. Installation des dépendances Python conteneurisées, versions exactes de uv.lock
#    (--frozen : le build échoue si uv.lock est périmé, jamais de résolution à la volée).
#    Dépendances du projet seulement, sans les outils de dev.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_PREFERENCE=only-system \
    PATH=/opt/venv/bin:$PATH
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.13.1 && \
    uv sync --frozen --no-dev --no-install-project && \
    pip uninstall -y uv

# 3. Copie du code source, des ressources web / templates et de l'application Vue compilée
COPY src/ ./src/
COPY web/ ./web/
COPY --from=frontend /build/frontend/dist ./frontend/dist/
COPY VERSION ./VERSION

# 4. Création d'un utilisateur non-root pour la sécurité et attribution des droits
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

USER appuser

# 4. Port d'écoute Cloud Run (défaut 8080)
EXPOSE 8080

# 5. Sonde de santé interne
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; port = os.environ.get('PORT', '8080'); urllib.request.urlopen('http://127.0.0.1:' + port + '/health')"

# 6. Lancement du serveur FastAPI avec Uvicorn
CMD ["sh", "-c", "exec uvicorn server:app --app-dir /app/src --host 0.0.0.0 --port ${PORT:-8080}"]
