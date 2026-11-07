"""scripts/setup_cloud_scheduler.sh sets up the job with what the app accepts: same account, audience, route."""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # noqa: S404 - runs bash on the repository's own script

import pytest

from infrastructure.security import api_auth
from services.competitions.results_batch import DEFAULT_TIME_BUDGET_SECONDS

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "setup_cloud_scheduler.sh")


def _settings() -> dict[str, str]:
    with open(SCRIPT, encoding="utf-8") as script:
        return dict(re.findall(r'^([A-Z_]+)="([^"$]*)"$', script.read(), re.MULTILINE))


def test_token_matches_what_the_app_accepts() -> None:
    settings = _settings()
    account = f"{settings['SERVICE_ACCOUNT_NAME']}@{settings['EXPECTED_PROJECT']}.iam.gserviceaccount.com"
    assert account == api_auth.DEFAULT_SCHEDULER_SERVICE_ACCOUNT
    assert settings["AUDIENCE"] == api_auth.DEFAULT_SCHEDULER_AUDIENCE
    assert settings["EXPECTED_PROJECT"] == api_auth.DEFAULT_PROJECT_ID
    assert settings["ROUTE"] in api_auth.SCHEDULER_PATHS


def test_deadline_leaves_room_for_the_time_budget() -> None:
    deadline = int(_settings()["ATTEMPT_DEADLINE"].rstrip("s"))
    assert DEFAULT_TIME_BUDGET_SECONDS < deadline <= 300  # Cloud Run request timeout (deploy_cloud_run.sh)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
def test_script_parses_and_shows_its_usage() -> None:
    subprocess.run(["bash", "-n", SCRIPT], check=True)  # noqa: S603, S607 - fixed argv
    usage = subprocess.run(["bash", SCRIPT, "--help"], check=True, capture_output=True, text=True).stdout  # noqa: S603, S607
    assert "--dry-run" in usage and "--status" in usage
