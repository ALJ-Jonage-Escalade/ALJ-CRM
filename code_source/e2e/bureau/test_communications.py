"""Office portal, communications page: e-mail templates (create, edit, delete), variables, WhatsApp text."""
import pytest
from playwright.sync_api import expect

from helpers.auth import login_as
from helpers.data import unique_name


def _open(page, role="admin"):
    with page.expect_response(lambda r: r.url.endswith("/api/whatsapp-template") and r.request.method == "GET",
                              timeout=20_000) as whatsapp:
        page.goto("/bureau/communications")
        login_as(page, role)
    expect(page.get_by_test_id("template-select").locator("option").first).to_be_attached(timeout=20_000)
    # Loaded apart from the templates: once shown, it can no longer overwrite a fill() of the test
    expect(page.get_by_test_id("whatsapp")).to_have_value(whatsapp.value.json().get("template") or "")
    return page


def _options(page, name):
    return page.get_by_test_id("template-select").locator("option").filter(has_text=name)


def _create(page, name):
    page.get_by_test_id("template-new").click()
    page.get_by_test_id("new-template-name").fill(name)
    page.get_by_test_id("new-template-create").click()
    expect(page.get_by_test_id("toast")).to_contain_text(f"Nouveau modèle « {name} » créé")
    expect(page.get_by_test_id("template-select")).to_have_value(name)


@pytest.fixture
def accept_with(page):
    """Accepts confirm() boxes and answers prompt() boxes with the given text."""
    answer = {"text": ""}
    page.on("dialog", lambda dialog: dialog.accept(answer["text"]) if dialog.type == "prompt" else dialog.accept())
    return answer


def test_template_lifecycle(page, accept_with):
    """Create, edit (kept after a reload), rename, delete."""
    _open(page)
    name = unique_name("E2E Template")
    _create(page, name)
    expect(page.get_by_test_id("subject")).to_have_value("Sujet du courriel")

    page.get_by_test_id("subject").fill("Training camp for {first_name}")
    page.get_by_test_id("body").fill("Hello {first_name}, see you at the camp.")
    page.get_by_test_id("sender-email").fill("competitions@alj-escalade.fr")
    page.get_by_test_id("template-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text(f"Modèle « {name} » enregistré")

    page.reload()
    _open(page)
    page.get_by_test_id("template-select").select_option(name)
    expect(page.get_by_test_id("subject")).to_have_value("Training camp for {first_name}")
    expect(page.get_by_test_id("body")).to_have_value("Hello {first_name}, see you at the camp.")
    expect(page.get_by_test_id("sender-email")).to_have_value("competitions@alj-escalade.fr")

    renamed = unique_name("E2E Renamed")
    page.get_by_test_id("template-name").fill(renamed)
    page.get_by_test_id("template-save").click()
    expect(page.get_by_test_id("template-select")).to_have_value(renamed)
    expect(_options(page, name)).to_have_count(0)

    page.get_by_test_id("template-delete").click()
    expect(page.get_by_test_id("toast")).to_contain_text(f"Modèle « {renamed} » supprimé")
    expect(_options(page, renamed)).to_have_count(0)


def test_delete_needs_confirmation(page):
    _open(page)
    name = unique_name("E2E Template")
    _create(page, name)
    page.on("dialog", lambda dialog: dialog.dismiss())
    page.get_by_test_id("template-delete").click()
    expect(page.get_by_test_id("template-select")).to_have_value(name)
    page.reload()
    _open(page)
    expect(_options(page, name)).to_have_count(1)


def test_duplicate_name_refused(page, accept_with):
    _open(page)
    existing = page.get_by_test_id("template-select").input_value()
    page.get_by_test_id("template-new").click()
    page.get_by_test_id("new-template-name").fill(existing.upper())
    page.get_by_test_id("new-template-create").click()
    expect(page.get_by_test_id("toast")).to_contain_text("existe déjà")


def test_subject_and_sender_are_required(page, accept_with):
    _open(page)
    _create(page, unique_name("E2E Template"))
    page.get_by_test_id("subject").fill("")
    page.get_by_test_id("template-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("sujet et le corps du message sont obligatoires")
    page.get_by_test_id("subject").fill("Subject")
    page.get_by_test_id("sender-email").fill("not-an-address")
    page.get_by_test_id("template-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("adresse e-mail valide")


def test_variables_formatting_and_preview(page, accept_with):
    _open(page)
    _create(page, unique_name("E2E Template"))
    body = page.get_by_test_id("body")
    body.fill("")
    page.get_by_test_id("variables-toggle").click()
    page.get_by_test_id("variables").get_by_role("button", name="{first_name}").click()
    expect(body).to_have_value("{first_name}")
    # Live preview renders the variables with the demo member
    expect(page.get_by_test_id("preview-body")).to_have_text("Alex")
    page.get_by_test_id("subject").fill("Licence {num_licence}")
    expect(page.get_by_test_id("preview-subject")).to_have_text("Licence 847291")
    page.get_by_test_id("sender-name").fill("ALJ Compétitions")
    page.get_by_test_id("sender-email").fill("competitions@alj-escalade.fr")
    expect(page.get_by_test_id("preview-from")).to_have_text("ALJ Compétitions <competitions@alj-escalade.fr>")

    body.fill("")
    page.get_by_test_id("format-bold").click()
    expect(body).to_have_value("<b>texte</b>")
    body.fill("")
    accept_with["text"] = "https://www.alj-escalade.fr"
    page.get_by_test_id("format-link").click()
    expect(body).to_have_value('<a href="https://www.alj-escalade.fr">texte</a>')

    page.get_by_test_id("signature").uncheck()
    expect(page.get_by_test_id("preview-signature")).to_be_hidden()


def test_whatsapp_text(page):
    _open(page)
    text = unique_name("Join the WhatsApp group of your slot:")
    page.get_by_test_id("whatsapp").fill(text)
    page.get_by_test_id("whatsapp-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Texte WhatsApp enregistré")
    page.reload()
    _open(page)
    expect(page.get_by_test_id("whatsapp")).to_have_value(text)


def test_coach_is_refused(page):
    """Communications is for admins only: back to Accueil (see e2e/bureau/test_accueil.py). The API refusing a
    coach's writes is checked by tests/web/test_bureau_web.py (API auth is off in dev mode)."""
    page.goto("/bureau/communications")
    login_as(page, "coach")
    page.wait_for_url("**/bureau/?reserve=/bureau/communications")
    expect(page.get_by_test_id("template-select")).to_have_count(0)
