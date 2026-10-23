"""Native confirm() / prompt() boxes of the pages."""
from playwright.sync_api import Page


def accept_dialogs(page: Page) -> None:
    """confirm() boxes (delete, archive…) are dismissed by Playwright unless accepted."""
    page.on("dialog", lambda dialog: dialog.accept())
