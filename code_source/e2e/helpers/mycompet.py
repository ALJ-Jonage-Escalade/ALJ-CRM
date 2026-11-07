"""Client of the fake MyCompet (e2e/fakes/mycompet_fake.py)."""
import json
import urllib.request

FAKE_PORT = 8096
FAKE_URL = f"http://localhost:{FAKE_PORT}"

SERVER_ENV = {
    "MYCOMPET_BASE_URL": FAKE_URL,
    "FFME_ARCHIVES_URL": f"{FAKE_URL}/archives",
}


class FakeMyCompet:
    def set(self, competitions: list) -> None:
        """competitions: [{"number", "title", "venue", "date" (ISO), "in_archive", "club_athletes": [...]}]."""
        body = json.dumps({"competitions": competitions}).encode()
        req = urllib.request.Request(f"{FAKE_URL}/_e2e/state", data=body, method="PUT",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()

    def clear(self) -> None:
        self.set([])
