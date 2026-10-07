# GitHub Actions Workflows

Six thin callers. The jobs themselves live in
[ChiefGyk3D/git-your-ship-together](https://github.com/ChiefGyk3D/git-your-ship-together),
shared with the rest of the maintainer's repositories, so a pipeline fix or a
new scan step lands once. Every caller pins the same tag of that repository
(`# vX.Y.Z` beside the commit); Dependabot proposes the next tag a week after
it is cut, and a release note that asks callers to re-pin is done by hand. Each file here says only what is
specific to Penguin Overlord: Python versions, the test command and its
coverage floor, the image checks, the Doppler project.

| Workflow | Triggers | Calls | What it does |
|---|---|---|---|
| `ci.yml` | push to main/develop/copilot/**, PRs, manual | `python-ci.yml` | Lint (ruff), tests on Python 3.10–3.14 with a 29% coverage floor and `pip check`, Docker build with the core-import, every-cog-imports and healthcheck checks, one `CI green` gate job for branch protection |
| `release.yml` | push to main, `v*.*.*` tags, PRs, weekly, manual | `container-release.yml` | Build and test on every PR; on main and tags publish a multi-arch (amd64 + arm64) image to `ghcr.io/chiefgyk3d/penguin-overlord`, signed with cosign, with a syft SBOM attached and SLSA provenance recorded; Trivy scan to the Security tab |
| `security.yml` | push to main/develop, PRs, weekly, manual | `security.yml` | CodeQL (`security-extended,security-and-quality`), gitleaks over the full history, pip-audit, dependency review on PRs, Snyk weekly |
| `verify.yml` | daily, manual | `verify-published.yml` | Pulls the published `latest` image on both platforms and verifies its cosign signature, SBOM attestation and provenance from outside, then runs the same import and healthcheck checks the release ran |
| `dependabot-auto-merge.yml` | PRs | `dependabot-auto-merge.yml` | Queues a Dependabot bump to merge itself once `CI green` passes; a major bump is left for a person |
| `project-sync.yml` | issue and pull request events, weekly, manual | `project-sync.yml` | Adds this repository's issues and pull requests to the Renegade-Penguin suite board with Area `Penguin Overlord`, sets Status by event, stamps the done date, reconciles weekly. Needs the board-side setup in `docs/superpowers/plans/2026-10-07-board-and-gyst-onboarding.md` before it goes green |

## Secrets: Doppler, not GitHub

No secret is stored in this repository's GitHub secrets. A job authenticates
to Doppler with a short-lived token minted from its own GitHub OIDC identity
(a Doppler Service Account Identity) and reads the `ci` config of the shared
`ci` Doppler project, which holds only what the pipelines need:

| Name | Used by |
|---|---|
| `SNYK_TOKEN` | `security.yml`, Snyk |

The bot's runtime secrets live in that project's other configs (`prd`, ...)
and never in `ci`: every value in the config a job reads is exported into the
job's environment.

The per-repository settings are **repository variables** (Settings → Secrets
and variables → Actions → Variables), identifiers rather than secrets:

| Variable | Used by |
|---|---|
| `DOPPLER_IDENTITY_ID` | `ci.yml`, `security.yml`, `release.yml`: the UUID of the identity that reads the `ci` config |
| `PROJECTS_APP_CLIENT_ID` | `project-sync.yml`: the Client ID of the board App |
| `PROJECTS_DOPPLER_IDENTITY_ID` | `project-sync.yml`: the UUID of the identity that reads `projects`/`prd`, which holds only the App's private key |

Before that is set the pipelines still run: Snyk warns and skips, and GHCR
publishing works regardless because it uses the job's own `GITHUB_TOKEN`.

The setup runbook, the fallback path (a Doppler Service Token as the single
GitHub secret `DOPPLER_TOKEN`), and every input are documented in the
git-your-ship-together README.

## Verifying a published image

```sh
cosign verify ghcr.io/chiefgyk3d/penguin-overlord:latest \
  --certificate-identity-regexp '^https://github.com/ChiefGyk3D/git-your-ship-together/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com

gh attestation verify oci://ghcr.io/chiefgyk3d/penguin-overlord:latest --owner ChiefGyk3D
```

The SBOM is also attached to every run of `release.yml` as the
`sbom.spdx.json` artifact.

## Image tags

- `latest` (main branch only)
- `1.2.3`, `1.2`, `1` (from `v1.2.3` tags)
- `main`, `sha-<short>` (branch and commit)
- `pr-123` (pull requests; built and tested, never pushed)

## Dependabot

`dependabot.yml` opens weekly PRs for Python packages, the Docker base image
(pinned by digest in `Dockerfile`) and GitHub Actions, each with a seven-day
cooldown on new releases.

## Status badges

```markdown
[![CI](https://github.com/ChiefGyk3D/penguin-overlord/actions/workflows/ci.yml/badge.svg)](https://github.com/ChiefGyk3D/penguin-overlord/actions/workflows/ci.yml)
[![Release](https://github.com/ChiefGyk3D/penguin-overlord/actions/workflows/release.yml/badge.svg)](https://github.com/ChiefGyk3D/penguin-overlord/actions/workflows/release.yml)
[![Security](https://github.com/ChiefGyk3D/penguin-overlord/actions/workflows/security.yml/badge.svg)](https://github.com/ChiefGyk3D/penguin-overlord/actions/workflows/security.yml)
```

## What changed in the migration

- `ci-tests.yml`, `docker-build-publish.yml`, `codeql-analysis.yml`,
  `dependency-review.yml`, `dependency-scan.yml` and `snyk-security.yml` were
  replaced by the callers above.
- Bandit was dropped as a separate step. Ruff's `S` rules are bandit's checks;
  they run in the lint job as an advisory second pass (42 findings today,
  tracked for cleanup) while the existing rule set keeps gating, exactly as
  before. Move `S` into `pyproject.toml`'s `select` once the tree is clean.
- pip-audit gates (it was advisory; the pinned set is clean).
- Python 3.14 is a required leg rather than experimental; it has passed on
  every run since it was added, and the image runs on it.
- `.gitleaks.toml` allowlists the one documented placeholder (the truncated
  `Token preview: MTIz...` example in the initial commit's docs), so gitleaks
  fails only on a real credential.
- Images are now signed, carry an SBOM and provenance, and `latest` is
  rebuilt weekly so base-image fixes reach it between commits.
