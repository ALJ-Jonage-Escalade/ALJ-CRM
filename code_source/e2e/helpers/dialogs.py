"""Confirmation boxes of the pages (UiDialogHost: the themed dialog that replaced the native confirm())."""
from playwright.sync_api import Page


def accept_dialogs(page: Page) -> None:
    """Confirms every confirmation box (delete, archive…) as soon as it shows up."""
    confirm = page.get_by_test_id("dialog-confirm")
    page.add_locator_handler(confirm, lambda: confirm.click())
