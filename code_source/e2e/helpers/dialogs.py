"""Confirmation and text-entry boxes of the pages (UiDialogHost: the themed dialog that replaced confirm() and prompt())."""
from playwright.sync_api import Page, expect


def accept_dialogs(page: Page) -> None:
    """Confirms every confirmation box (delete, archive…) as soon as it shows up."""
    confirm = page.get_by_test_id("dialog-confirm")
    page.add_locator_handler(confirm, lambda: confirm.click())


def confirm_dialog(page: Page, message: str = "") -> None:
    """Waits for the box (checking its message when given) and confirms it."""
    if message:
        expect(page.get_by_test_id("dialog-message")).to_have_text(message)
    page.get_by_test_id("dialog-confirm").click()
    expect(page.get_by_test_id("dialog-host")).to_be_hidden()


def cancel_dialog(page: Page, message: str = "") -> None:
    """Waits for the box (checking its message when given) and answers « Annuler »."""
    if message:
        expect(page.get_by_test_id("dialog-message")).to_have_text(message)
    page.get_by_test_id("dialog-cancel").click()
    expect(page.get_by_test_id("dialog-host")).to_be_hidden()


def answer_prompt(page: Page, text: str) -> None:
    """Fills the text-entry box and confirms it."""
    page.get_by_test_id("dialog-input").fill(text)
    confirm_dialog(page)
