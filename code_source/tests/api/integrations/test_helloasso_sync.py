"""POST /api/helloasso/sync: the campaign must be read completely before anything is written, since the automatic
links are recomputed from the items read (a partial read would unlink the payments it missed)."""

from __future__ import annotations

from unittest.mock import patch

from infrastructure.firestore.app_settings import HELLOASSO_COMPETITION_CAMPAIGN, AppSettingsRepository
from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
from infrastructure.helloasso.api import HelloAssoApiError
from support.api_case import ApiTestCase

FETCH = "services.competitions.helloasso_items.fetch_form_items"


class TestHelloAssoSync(ApiTestCase):

    def test_no_campaign_chosen(self) -> None:
        with patch(FETCH) as fetch:
            r = self.client.post("/api/helloasso/sync")
        self.assertEqual((r.status_code, r.json()["code"]), (400, "no_campaign"))
        fetch.assert_not_called()

    def test_helloasso_failure_writes_nothing(self) -> None:
        AppSettingsRepository.save(HELLOASSO_COMPETITION_CAMPAIGN, "Event:competitions-2026-2027")
        for failure in (HelloAssoApiError("API HelloAsso injoignable : ReadTimeout"),
                        HelloAssoApiError("Identifiants manquants.", "helloasso_credentials_missing")):
            with self.subTest(code=failure.code), patch(FETCH, side_effect=failure), \
                 patch.object(Repo, "sync_helloasso_mirror") as mirror, patch.object(Repo, "replace_auto_links") as relink:
                r = self.client.post("/api/helloasso/sync")
            self.assertEqual((r.status_code, r.json()["code"]), (502, failure.code))
            self.assertIn("Rien n'a été modifié", r.json()["message"])
            mirror.assert_not_called()
            relink.assert_not_called()

    def test_campaign_read_and_linked(self) -> None:
        AppSettingsRepository.save(HELLOASSO_COMPETITION_CAMPAIGN, "Event:competitions-2026-2027")
        with patch(FETCH, return_value=[]) as fetch:
            r = self.client.post("/api/helloasso/sync")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["stats"]["nb_items"], 0)
        fetch.assert_called_once_with("Event", "competitions-2026-2027")
