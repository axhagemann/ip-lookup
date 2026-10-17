# GHCR Image Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CI builds the `app` image on every push to `main` and pushes it to GitHub Container Registry; the server pulls that image instead of building it.

**Architecture:** A new workflow `.github/workflows/image.yml` runs the existing test suites, then builds the repo's `Dockerfile` with Buildx and pushes `ghcr.io/axhagemann/ip-lookup` tagged `sha-<7 chars>` and `latest`. Pull requests run the same jobs but never log in or push. In `docker-compose.yml`, `app` gets `image: ghcr.io/axhagemann/ip-lookup:${APP_TAG:-latest}` next to the existing `build: .`, so local `--build` still works and `APP_TAG` in the server's `.env` pins a release for rollback.

**Tech Stack:** GitHub Actions (`docker/setup-buildx-action@v3`, `docker/login-action@v3`, `docker/metadata-action@v5`, `docker/build-push-action@v6`, `actions/setup-python@v5`, `actions/setup-node@v4`), Docker Compose v2, pytest + PyYAML (already installed transitively via `uvicorn[standard]`).

**Spec:** None. Decisions come from the 2026-10-17 conversation and are recorded under *Decisions* below.

## Decisions

- **Registry:** GHCR. The repo is already on GitHub, and the workflow authenticates with the built-in `GITHUB_TOKEN`, so no extra secrets are needed.
- **Visibility: public package.** The image contains only `main.py`, `geo.py`, `upcheck.py`, `requirements.txt` and `static/`. The GeoLite2 databases live on a volume and the MaxMind credentials stay in the server's `.env`, so the image holds nothing secret or licence-restricted. A public package means the server needs no `docker login`. *If you want it private instead:* skip Task 3 Step 2 and run `docker login ghcr.io -u axhagemann` on the server once, with a classic PAT that has only `read:packages`.
- **Tags:** `sha-<short sha>` for every main build, plus `latest` on the default branch. No semver; the site has no releases.
- **Platform:** `linux/amd64` only. Confirm the server's architecture in Task 3 Step 1.
- **CI gate:** the image job `needs:` the test job, so a red build never publishes.
- **No `ruff format --check` in CI:** ruff 0.16 also formats Python blocks inside Markdown, and three committed `.md` files (`README.md`, `PLAN-up-geo.md`, `docs/superpowers/plans/2026-10-06-light-theme-redesign.md`) would be reformatted. That check would fail on day one for reasons unrelated to this change. CI runs `ruff check .` only.

## Global Constraints

- Do not commit, push or open PRs. The user commits themselves. Each task ends with changes left uncommitted.
- Do not install tools ad hoc. Use the existing `.venv` (`source .venv/bin/activate`) for pytest and ruff. Node is not installed locally, so `node --test` runs in CI only.
- Locally, run ruff with `--no-cache`: `.ruff_cache/` is not writable for this user.
- Keep the existing compose comment style: a short "why" comment above any non-obvious key.
- Don't touch `nginx`, `goatcounter`, `certbot` or `geoipupdate` in `docker-compose.yml`. Don't touch `bootstrap.sh`: its plain `docker compose up -d` keeps working, because compose pulls the image if it's absent.

## Review Focus

1. **Package left private after the first push.** The server's anonymous pull then fails with `unauthorized` / `denied`. Task 3 Step 3 checks this with an anonymous pull from a logged-out Docker.
2. **The server keeps running a stale image.** `docker compose up -d` alone doesn't re-pull an existing `:latest`. The documented deploy command must be `docker compose pull app` before `up -d`, and Task 3 Step 4 confirms the running container's `org.opencontainers.image.revision` label matches `git rev-parse HEAD`.
3. **Failing tests still publish an image.** Pinned by `test_image_job_waits_for_tests` (Task 2).
4. **A pull request pushes to the registry.** Pinned by `test_pull_requests_never_push` (Task 2).
5. **CI tests on a different Python than the image runs.** Pinned by `test_ci_python_matches_dockerfile` (Task 2), which compares `setup-python`'s version to the Dockerfile's `FROM python:X.Y-slim`.

---

### Task 1: Compose pulls the app image from GHCR

**Files:**
- Create: `tests/test_deploy.py`
- Modify: `docker-compose.yml:2-3` (the `app:` service header)

**Interfaces:**
- Produces: the image reference `ghcr.io/axhagemann/ip-lookup:${APP_TAG:-latest}`, the module-level constants `ROOT`, `IMAGE` and helper `load_yaml(path)` in `tests/test_deploy.py`, which Task 2 extends.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deploy.py`:

```python
"""Guards for the registry deploy.

See docs/superpowers/plans/2026-10-17-ghcr-image-registry.md. CI pushes the app
image to GHCR and the server pulls it, so docker-compose.yml and the workflow
must agree on the image name, and the workflow must never publish untested or
pull-request code.
"""

from pathlib import Path

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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_deploy.py -v`
Expected: `test_app_pulls_from_ghcr` and `test_app_tag_defaults_to_latest_and_is_overridable` FAIL with `KeyError: 'image'`. `test_app_still_builds_locally` PASSES.

- [ ] **Step 3: Add the image reference to compose**

In `docker-compose.yml`, replace:

```yaml
  app:
    build: .
```

with:

```yaml
  app:
    # Built and pushed by .github/workflows/image.yml on every push to main;
    # the server pulls it (`docker compose pull app`). `build: .` stays so a
    # local `docker compose up --build` still works. Set APP_TAG=sha-<7 chars>
    # in .env to pin or roll back a release.
    image: ghcr.io/axhagemann/ip-lookup:${APP_TAG:-latest}
    build: .
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_deploy.py -v`
Expected: 3 passed.

Run: `docker compose config --images`
Expected: `ghcr.io/axhagemann/ip-lookup:latest` is listed alongside the other services' images. If `docker` isn't available locally, skip this check and note it in the handoff.

- [ ] **Step 5: Run the full suite and lint**

Run: `python -m pytest -q && ruff check --no-cache .`
Expected: all tests pass (285 before this plan, plus the new ones); `All checks passed!`

- [ ] **Step 6: Leave the changes uncommitted**

Don't commit. Report the changed files: `docker-compose.yml`, `tests/test_deploy.py`.

---

### Task 2: Workflow builds, tests and pushes the image, plus deploy docs

**Files:**
- Create: `.github/workflows/image.yml`
- Modify: `tests/test_deploy.py` (append the workflow tests)
- Modify: `README.md:228-233` (*Subsequent deploys*), plus a new *Rolling back* subsection directly after it
- Modify: `CLAUDE.md` (*Docker (mirrors production)* block in *Commands*)

**Interfaces:**
- Consumes: `ROOT`, `IMAGE` and `load_yaml(path)` from `tests/test_deploy.py` (Task 1).
- Produces: workflow job ids `test` and `image`; the build step has `id: build`; the metadata step has `id: meta`.

- [ ] **Step 1: Write the failing workflow tests**

Add `import re` to the top of `tests/test_deploy.py`, above `from pathlib import Path`. Ruff's `I` rule is enabled in `pyproject.toml`, and it wants stdlib `import` lines before `from` lines. Then append:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_deploy.py -v`
Expected: collection error, `FileNotFoundError: ... .github/workflows/image.yml`.

- [ ] **Step 3: Create the workflow**

Create `.github/workflows/image.yml`:

```yaml
# Builds the app image and pushes it to GHCR on every push to main. The server
# pulls it instead of building (see README "Subsequent deploys"). Pull requests
# run the same tests and build but never log in or push.

name: Image

on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]
  workflow_dispatch:

concurrency:
  group: image-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    name: Tests
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      # Keep in step with the Dockerfile's FROM line (tests/test_deploy.py checks).
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "22"

      - run: pip install -r requirements-dev.txt
      - run: ruff check .
      - run: python -m pytest
      - run: node --test

  image:
    name: Build and push
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        if: github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      # sha-<7 chars> on every build, latest only from main. Also sets the
      # org.opencontainers.image.source label, which links the package to
      # this repo on GitHub.
      - name: Image metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha
            type=raw,value=latest,enable={{is_default_branch}}

      - name: Build and push
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_deploy.py -v`
Expected: 11 passed (3 from Task 1 + 8 workflow tests).

- [ ] **Step 5: Update the README deploy section**

In `README.md`, replace:

````markdown
### Subsequent deploys

```bash
git pull
docker compose up -d --build
```
````

with:

````markdown
### Subsequent deploys

Every push to `main` runs the tests and, if they pass, pushes the app image to `ghcr.io/axhagemann/ip-lookup` (`.github/workflows/image.yml`). Wait for that workflow to go green, then on the server:

```bash
git pull                     # nginx config and compose file still come from the repo
docker compose pull app
docker compose up -d
```

`docker compose up -d` on its own does not re-pull an image it already has, so don't skip the `pull`. To build on the server instead (for example while GitHub is down), `docker compose up -d --build` still works.

### Rolling back

Each build is also tagged `sha-<first 7 chars of the commit>`. Pin one in `.env` and restart:

```bash
echo 'APP_TAG=sha-1a2b3c4' >> .env
docker compose up -d
```

Remove the `APP_TAG` line to go back to `latest`.
````

- [ ] **Step 6: Update CLAUDE.md's Docker commands**

In `CLAUDE.md`, replace:

````markdown
Docker (mirrors production):

```bash
docker compose up -d --build
````

with:

````markdown
Docker (mirrors production — the server pulls the `app` image from `ghcr.io/axhagemann/ip-lookup`, built by `.github/workflows/image.yml`; locally, `--build` builds it from source instead):

```bash
docker compose up -d --build
````

- [ ] **Step 7: Run the full suite and lint**

Run: `python -m pytest -q && ruff check --no-cache .`
Expected: all tests pass; `All checks passed!`

- [ ] **Step 8: Leave the changes uncommitted**

Don't commit. Report the changed files: `.github/workflows/image.yml`, `tests/test_deploy.py`, `README.md`, `CLAUDE.md`.

---

### Task 3: Rollout (manual, done by the user)

These steps need GitHub UI access and the server, so the implementer only hands them over. They run after the user has committed and pushed Tasks 1–2.

- [ ] **Step 1: Confirm the server architecture**

On the server: `uname -m`
Expected: `x86_64`. If it prints `aarch64`, change `platforms` in `image.yml` and the expected value in `test_image_is_built_for_the_server_arch` to `linux/arm64` before the first push.

- [ ] **Step 2: Make the package public after the first green run**

GitHub → your profile → Packages → `ip-lookup` → Package settings → Change visibility → Public. Under "Manage Actions access", check that `axhagemann/ip-lookup` is listed with the Write role; the source label normally adds it automatically.

- [ ] **Step 3: Verify an anonymous pull works**

```bash
docker logout ghcr.io
docker pull ghcr.io/axhagemann/ip-lookup:latest
```

Expected: the pull succeeds. `unauthorized` or `denied` means the package is still private (see Step 2).

- [ ] **Step 4: Switch the server over and confirm the running revision**

```bash
git pull
docker compose pull app && docker compose up -d --no-build
docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$(docker compose ps -q app)"
git rev-parse HEAD
```

Expected: the two hashes match. Then `curl -s https://alexander-hagemann.de/health` returns OK.

- [ ] **Step 5: Try a rollback once**

Set `APP_TAG=sha-<previous build's 7 chars>` in `.env`, run `docker compose pull app && docker compose up -d --no-build`, and check that the revision label from Step 4 changes. Then remove the line and run the same command again.
