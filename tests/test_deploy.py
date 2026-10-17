"""Guards for the registry deploy.

See docs/superpowers/plans/2026-10-17-ghcr-image-registry.md. CI pushes the app
image to GHCR and the server pulls it, so docker-compose.yml and the workflow
must agree on the image name, and the workflow must never publish untested or
pull-request code.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "ghcr.io/axhagemann/ip-lookup"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


APP = load_yaml(ROOT / "docker-compose.yml")["services"]["app"]


def test_app_pulls_from_ghcr():
    assert APP["image"].startswith(IMAGE + ":")


def test_app_tag_defaults_to_latest_and_is_overridable():
    # APP_TAG in the server's .env pins a release (sha-<7 chars>) for rollback.
    assert APP["image"] == IMAGE + ":${APP_TAG:-latest}"


def test_app_still_builds_locally():
    # `docker compose up --build` on a dev machine must keep working.
    assert APP["build"] == "."


WORKFLOW = load_yaml(ROOT / ".github" / "workflows" / "image.yml")
JOBS = WORKFLOW["jobs"]
# PyYAML follows YAML 1.1, where a bare `on:` key parses as boolean True.
TRIGGERS = WORKFLOW.get("on", WORKFLOW.get(True))


def step(job: str, uses_prefix: str) -> dict:
    matches = [s for s in JOBS[job]["steps"] if s.get("uses", "").startswith(uses_prefix)]
    assert len(matches) == 1, f"expected one {uses_prefix} step in {job}"
    return matches[0]


def run_commands(job: str) -> str:
    return "\n".join(s.get("run", "") for s in JOBS[job]["steps"])


def test_workflow_runs_on_main_and_pull_requests():
    assert TRIGGERS["push"]["branches"] == ["main"]
    assert TRIGGERS["pull_request"]["branches"] == ["main"]


def test_test_job_runs_every_suite():
    cmds = run_commands("test")
    assert "pip install -r requirements-dev.txt" in cmds
    assert "ruff check ." in cmds
    assert "python -m pytest" in cmds
    assert "node --test" in cmds


def test_ci_python_matches_dockerfile():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    image_python = re.search(r"^FROM python:(\d+\.\d+)", dockerfile, re.M).group(1)
    ci_python = str(step("test", "actions/setup-python")["with"]["python-version"])
    assert ci_python == image_python


def test_image_job_waits_for_tests():
    assert JOBS["image"]["needs"] == "test"


def test_only_image_job_can_write_packages():
    assert JOBS["image"]["permissions"] == {"contents": "read", "packages": "write"}
    assert JOBS["test"]["permissions"] == {"contents": "read"}
    assert "permissions" not in WORKFLOW or WORKFLOW["permissions"] == {}


def test_pull_requests_never_push():
    not_pr = "${{ github.event_name != 'pull_request' }}"
    assert step("image", "docker/login-action")["if"] == "github.event_name != 'pull_request'"
    assert step("image", "docker/build-push-action")["with"]["push"] == not_pr


def test_image_name_and_tags():
    meta = step("image", "docker/metadata-action")["with"]
    assert meta["images"] == "ghcr.io/${{ github.repository }}"
    tags = meta["tags"].split()
    assert "type=sha" in tags
    assert "type=raw,value=latest,enable={{is_default_branch}}" in tags


def test_image_is_built_for_the_server_arch():
    assert step("image", "docker/build-push-action")["with"]["platforms"] == "linux/amd64"


def readme_section(heading: str) -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    return readme.split(f"### {heading}\n", 1)[1].split("\n### ", 1)[0]


@pytest.mark.parametrize("heading", ["Subsequent deploys", "Rolling back"])
def test_documented_deploys_never_fall_back_to_building(heading):
    # With `build: .` in compose, a failed pull (typo'd APP_TAG, private
    # package, GHCR down) makes `up` build the local checkout and tag it as the
    # requested image. `&&` stops on a failed pull; `--no-build` turns a missing
    # image into an error instead of a silent local build.
    assert "docker compose pull app && docker compose up -d --no-build" in readme_section(heading)
