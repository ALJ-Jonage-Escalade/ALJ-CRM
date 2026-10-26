"""
Publishes the results of the seeded competitions on the fake MyCompet (e2e/fakes/mycompet_fake.py), so the
daily results batch can be tried on the dev stack without reaching the real site:

    uvicorn mycompet_fake:app --app-dir e2e/fakes --port 8096       # in another terminal
    set -a && source dev/dev.env && set +a
    export MYCOMPET_BASE_URL=http://localhost:8096 FFME_ARCHIVES_URL=http://localhost:8096/archives
    uv run python dev/seed/mycompet_state.py
    uv run dev/run_server.sh                                          # same MYCOMPET_BASE_URL / FFME_ARCHIVES_URL

Every ended competition gets a results page listed in the archive at its date, its first three
participants ranked 1st to 3rd. Dev mode only (the emulator); the URLs must point to this machine.
"""
import json
import os
import sys
import urllib.request
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

import datetime  # noqa: E402

from infrastructure import runtime_env  # noqa: E402
from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo  # noqa: E402

FIRST_NUMBER = 99_000  # fake results page numbers


def main() -> int:
    if not runtime_env.is_dev():
        print("❌ Dev mode only: source dev/dev.env first.", file=sys.stderr)
        return 1
    fake = runtime_env.mycompet_base_url()
    if (urlparse(fake).hostname or "").lower() not in ("localhost", "127.0.0.1", "::1"):
        print("❌ MYCOMPET_BASE_URL must point to the local fake MyCompet (http://localhost:8096).", file=sys.stderr)
        return 1
    today = datetime.date.today()
    published = []
    for number, doc in enumerate(Repo.list_competition_docs(), start=FIRST_NUMBER):
        ended = str(doc.get("date_fin") or doc.get("date_competition") or "")[:10]
        if not ended or datetime.date.fromisoformat(ended) > today:
            continue
        athletes = [{"nom": p.get("nom") or "", "prenom": p.get("prenom") or "", "licence": p.get("num_licence") or "",
                     "categorie": "U15 Femme", "classement": rank}
                    for rank, p in enumerate((doc.get("participants") or [])[:3], start=1)]
        published.append({"number": number, "title": doc.get("nom") or "", "venue": doc.get("lieu") or "Jonage",
                          "date": ended, "club_athletes": athletes})
    body = json.dumps({"competitions": published}).encode()
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(f"{fake}/_e2e/state", data=body, method="PUT", headers=headers)  # noqa: S310 - local fake (checked above)
    urllib.request.urlopen(request, timeout=10).read()  # noqa: S310 - local fake (checked above)
    for c in published:
        print(f"🏆 {c['title']} ({c['date']}): {len(c['club_athletes'])} club athlete(s) on resultat_{c['number']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
