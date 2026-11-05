"""Routes of src/api/integrations/helloasso_campaigns.py over the in-memory Firestore (auth off, local server)."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

from support.api_case import ApiTestCase

from api.integrations import helloasso_campaigns as route
from infrastructure.firestore.app_settings import COLLECTION, HELLOASSO_COMPETITION_CAMPAIGN, HELLOASSO_MEMBERSHIP_CAMPAIGN
from infrastructure.firestore.app_settings import AppSettingsRepository as Settings
from infrastructure.firestore.client import FirestoreError
from infrastructure.helloasso import form_activities
from infrastructure.helloasso.api import HelloAssoApiError

FORMS = [
    {"formSlug": "adhesion-2026", "formType": "Membership", "state": "Public", "title": "Adhésion 2026-2027",
     "startDate": "2026-09-01T00:00:00+02:00", "meta": {"createdAt": "2026-07-01T10:00:00+02:00"}},
    {"formSlug": "competitions-2026", "formType": "Event", "state": "Private", "title": "Compétitions 2026-2027",
     "activityType": "Compétition", "activityTypeId": 3, "startDate": "2026-09-15T00:00:00+02:00", "endDate": "2027-06-30T23:59:00+02:00"},
    {"formSlug": "competitions-2025", "formType": "Event", "state": "Disabled", "title": "Compétitions 2025-2026",
     "activityType": "Compétition", "activityTypeId": 3},
    {"formSlug": "soiree-club", "formType": "Event", "state": "Public", "title": "Soirée du club", "activityType": "Fête",
     "activityTypeId": 1},
]


class TestHelloAssoCampaigns(ApiTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.list_forms = self.patch_helloasso(return_value=FORMS)

    def patch_helloasso(self, **behaviour: Any) -> Any:  # Any: the mock
        for name, value in (("credentials_configured", True), ("require_access_token", "token")):
            patcher = patch.object(route.helloasso_api, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        form_activities.install(form_activities.ActivityCache(form_activities.CACHE_SECONDS))
        self.addCleanup(form_activities.install, None)
        listing = patch.object(route.helloasso_api, "list_forms", **behaviour)
        mock = listing.start()
        self.addCleanup(listing.stop)
        return mock

    def campaigns(self) -> Dict[str, Any]:  # Any: response body
        response = self.client.get("/api/helloasso/campaigns")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_lists_both_kinds_with_the_active_campaigns(self) -> None:
        Settings.save(HELLOASSO_MEMBERSHIP_CAMPAIGN, "Membership:adhesion-2026")
        Settings.save(HELLOASSO_COMPETITION_CAMPAIGN, "competitions-2025")  # bare slug saved in the past
        body = self.campaigns()
        self.assertIsNone(body["error"])
        self.assertEqual(body["membership"]["active"], {"form_type": "Membership", "slug": "adhesion-2026"})
        self.assertTrue(body["membership"]["configured"])
        self.assertEqual([(c["slug"], c["active"]) for c in body["membership"]["campaigns"]], [("adhesion-2026", True)])
        # The disabled active campaign is still listed, with a warning
        rows = {c["slug"]: c for c in body["competitions"]["campaigns"]}
        self.assertEqual(list(rows), ["competitions-2026", "competitions-2025"])
        self.assertEqual(rows["competitions-2025"]["warning"], "Campagne désactivée sur HelloAsso")
        self.assertIsNone(rows["competitions-2026"]["warning"])
        self.assertEqual([(c["slug"], c["activity_type"]) for c in body["others"]], [("soiree-club", "Fête")])
        types, states = self.list_forms.call_args.args
        self.assertEqual((sorted(types), sorted(states)), (["Event", "Membership"], ["Disabled", "Draft", "Private", "Public"]))

    def test_activities_read_from_the_details_once_then_cached(self) -> None:
        listed = [{key: value for key, value in form.items() if not key.startswith("activity")} for form in FORMS]
        self.list_forms.return_value = listed
        details = {form["formSlug"]: form for form in FORMS}
        with patch.object(route.helloasso_api, "get_public_form", side_effect=lambda _type, slug, _token: details[slug]) as read:
            first, second = self.campaigns(), self.campaigns()
        self.assertEqual(sorted(call.args[1] for call in read.call_args_list), ["competitions-2025", "competitions-2026", "soiree-club"])
        self.assertEqual(self.list_forms.call_args.kwargs, {"token": "token"})
        for body in (first, second):
            self.assertEqual([c["slug"] for c in body["competitions"]["campaigns"]], ["competitions-2026"])
            self.assertEqual([c["slug"] for c in body["others"]], ["soiree-club"])
            self.assertIsNone(body["warning"])

    def test_unreadable_activity_goes_to_others_with_a_warning(self) -> None:
        listed = [{key: value for key, value in form.items() if not key.startswith("activity")} for form in FORMS]
        self.list_forms.return_value = listed
        details = {form["formSlug"]: form for form in FORMS}

        def read(_type: str, slug: str, _token: str) -> Dict[str, Any]:  # Any: HelloAsso JSON
            if slug == "competitions-2026":
                raise HelloAssoApiError("API HelloAsso : HTTP 500")
            return details[slug]

        with patch.object(route.helloasso_api, "get_public_form", side_effect=read):
            body = self.campaigns()
        self.assertEqual(body["warning"], route._activities_unread(1))
        self.assertIsNone(body["error"])
        self.assertEqual([c["slug"] for c in body["others"]], ["soiree-club", "competitions-2026"])

    def test_membership_default_when_not_chosen(self) -> None:
        with patch.object(route, "get_target_slug", return_value="adhesion-env"):
            body = self.campaigns()
        self.assertEqual(body["membership"]["active"], {"form_type": "Membership", "slug": "adhesion-env"})
        self.assertFalse(body["membership"]["configured"])
        self.assertEqual((body["competitions"]["active"], body["competitions"]["configured"]), (None, False))
        self.assertFalse(any(c["active"] for c in body["competitions"]["campaigns"]))

    def test_helloasso_error_still_gives_the_active_campaigns(self) -> None:
        self.list_forms.side_effect = HelloAssoApiError("API HelloAsso : HTTP 500")
        Settings.save(HELLOASSO_COMPETITION_CAMPAIGN, "Event:competitions-2026")
        body = self.campaigns()
        self.assertEqual(body["error"], route.HELLOASSO_UNREACHABLE)
        self.assertEqual(body["competitions"]["active"], {"form_type": "Event", "slug": "competitions-2026"})
        self.assertEqual((body["membership"]["campaigns"], body["competitions"]["campaigns"], body["others"]), ([], [], []))

    def test_missing_credentials(self) -> None:
        with patch.object(route.helloasso_api, "credentials_configured", return_value=False):
            body = self.campaigns()
        self.assertEqual(body["error"], route.CREDENTIALS_MISSING)
        self.list_forms.assert_not_called()

    def test_firestore_unreadable_is_a_503(self) -> None:
        with patch.object(Settings, "get", side_effect=FirestoreError("down")):
            response = self.client.get("/api/helloasso/campaigns")
        self.assertEqual(response.status_code, 503)
        self.list_forms.assert_not_called()

    def test_choose_saves_type_and_slug(self) -> None:
        for kind, form_type, slug, key in (("membership", "Membership", "adhesion-2026", HELLOASSO_MEMBERSHIP_CAMPAIGN),
                                           ("competitions", "Event", "competitions-2026", HELLOASSO_COMPETITION_CAMPAIGN)):
            with self.subTest(kind=kind):
                response = self.client.put(f"/api/helloasso/campaigns/{kind}", json={"form_type": form_type, "slug": f" {slug} "})
                self.assertEqual((response.status_code, response.json()), (200, {"form_type": form_type, "slug": slug}))
                self.assertEqual(self.fake.store[COLLECTION][key]["value"], f"{form_type}:{slug}")
        self.assertTrue(self.campaigns()["competitions"]["campaigns"][0]["active"])

    def test_choose_refuses_a_wrong_shape(self) -> None:
        for kind, body in (("competitions", {"form_type": "Membership", "slug": "adhesion-2026"}),
                           ("membership", {"form_type": "Membership", "slug": "  "})):
            with self.subTest(body=body):
                response = self.client.put(f"/api/helloasso/campaigns/{kind}", json=body)
                self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.client.put("/api/helloasso/campaigns/donations", json={"form_type": "Donation", "slug": "x"}).status_code,
                         422)
        self.assertEqual(self.client.put("/api/helloasso/campaigns/membership", json={"slug": "x"}).status_code, 422)
        self.assertNotIn(HELLOASSO_MEMBERSHIP_CAMPAIGN, self.fake.store.get(COLLECTION, {}))
