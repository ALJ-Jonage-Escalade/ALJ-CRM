"""
Fake MyCompet results pages and FFME results archive for the e2e tests and the dev stack: the server
reaches it through MYCOMPET_BASE_URL / FFME_ARCHIVES_URL (honoured in dev mode only, see
infrastructure/runtime_env.py).

Pages are rendered from the anonymized template of the unit tests (tests/support/mycompet/), with the
competitions each test loads: PUT /_e2e/state {"competitions": [{"number", "title", "venue", "date",
"in_archive", "club_athletes": [{nom, prenom, licence, categorie, classement}]}]}.

    uvicorn mycompet_fake:app --app-dir e2e/fakes --port 8096
"""
import datetime
import os
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tests"))
from support.mycompet.render import render_archives, render_results  # noqa: E402

app = FastAPI(title="Fake MyCompet")
_state = {"competitions": []}


@app.put("/_e2e/state")
async def set_state(request: Request):
    body = await request.json()
    _state["competitions"] = list(body.get("competitions") or [])
    return {"competitions": len(_state["competitions"])}


@app.get("/archives", response_class=HTMLResponse)
def archives():
    return render_archives([
        {"number": c["number"], "title": c["title"], "venue": c["venue"], "date": datetime.date.fromisoformat(c["date"])}
        for c in _state["competitions"] if c.get("in_archive", True)])


@app.get("/resultat/resultat_{number}", response_class=HTMLResponse)
def results(number: int):
    found = next((c for c in _state["competitions"] if c["number"] == number), None)
    if found is None:
        raise HTTPException(404)
    return render_results(found["title"], found["venue"], found.get("club_athletes") or [])
