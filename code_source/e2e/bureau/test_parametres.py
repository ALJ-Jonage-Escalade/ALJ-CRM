"""Office portal, Paramètres page: Google connection (no Google account in dev mode), server cache, results batch.

The MyCompet detection (real FFME site) and the manual token check (real Google endpoint) are not run here."""
import pytest
from playwright.sync_api import expect

from helpers.auth import login_as
from helpers.dialogs import cancel_dialog, confirm_dialog

# The full rebuild replaces the server's cache: a setting saved meanwhile by another test of this file would be lost
pytestmark = pytest.mark.xdist_group("parametres")


def _open(page):
    page.goto("/bureau/parametres")
    login_as(page, "admin")
    expect(page.get_by_test_id("cache-status")).to_contain_text("Cache opérationnel")
    return page


def test_google_status_without_token(page):
    _open(page)
    expect(page.get_by_test_id("google-status")).to_contain_text("Non connecté")
    expect(page.get_by_test_id("google-account")).to_have_text("Non configuré")
    expect(page.get_by_test_id("db-mode")).to_contain_text("Firestore")

    page.get_by_test_id("google-test").click()
    report = page.get_by_test_id("google-test-report")
    expect(report).to_contain_text("🔴 Jeton OAuth2")
    expect(report).to_contain_text("Base de Données")
    expect(report).to_contain_text("Service Gmail API")
    expect(page.get_by_test_id("google-test")).to_be_enabled()


def test_server_cache_status(page):
    status = page.request.get("/api/cloud-db/status").json()
    _open(page)
    expect(page.get_by_test_id("cache-file")).to_contain_text(f"{status['member_count']} adhérents")
    expect(page.get_by_test_id("cache-pending")).to_have_text("0 (à jour)")
    expect(page.get_by_test_id("cache-last-sync")).not_to_have_text("Non renseignée")

    page.get_by_test_id("refresh").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Statuts réactualisés")
    expect(page.get_by_test_id("cache-status")).to_contain_text("Cache opérationnel")


def test_incremental_update_and_full_rebuild(page):
    _open(page)
    page.get_by_test_id("cache-sync").click()
    expect(page.get_by_test_id("toast")).to_contain_text("synchronisée avec succès")
    report = page.get_by_test_id("cache-report")
    expect(report).to_contain_text("Synchronisation réussie")
    expect(report).not_to_contain_text("reconstruction complète")

    page.get_by_test_id("troubleshooting").click()  # collapsed <details>
    page.get_by_test_id("cache-rebuild").click()
    confirm_dialog(page)
    expect(report).to_contain_text("(reconstruction complète)", timeout=30_000)
    # The rebuilt cache still holds every member
    status = page.request.get("/api/cloud-db/status").json()
    expect(page.get_by_test_id("cache-file")).to_contain_text(f"{status['member_count']} adhérents")
    assert status["member_count"] > 20


def test_full_rebuild_needs_confirmation(page):
    _open(page)
    page.get_by_test_id("troubleshooting").click()  # collapsed <details>
    page.get_by_test_id("cache-rebuild").click()
    cancel_dialog(page)
    expect(page.get_by_test_id("cache-report")).to_be_hidden()


def test_results_notification_email(page):
    _open(page)
    email = page.get_by_test_id("results-email")
    expect(email).not_to_have_value("")
    expect(page.get_by_test_id("results-last-run")).not_to_have_text("—")
    previous = email.input_value()
    try:
        email.fill("pas-une-adresse")
        page.get_by_test_id("results-email-save").click()
        expect(page.get_by_test_id("toast")).to_contain_text("adresse e-mail valide")

        email.fill("resultats.e2e@hogwarts.example")
        page.get_by_test_id("results-email-save").click()
        expect(page.get_by_test_id("toast")).to_contain_text("Adresse de notification enregistrée")
        page.reload()
        expect(page.get_by_test_id("results-email")).to_have_value("resultats.e2e@hogwarts.example")
    finally:
        # API auth is off in dev mode (dev/dev.env)
        page.request.post("/api/settings/competitions-results", data={"notification_email": previous})


def test_manual_token_is_required(page):
    _open(page)
    page.get_by_test_id("manual-token-open").click()
    page.get_by_test_id("manual-token-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("refresh_token valide")

