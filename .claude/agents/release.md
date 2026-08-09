---
name: release
description: Release a new version of doctorlib-navigator. Bumps Chart.yaml version+appVersion, pushes a semver tag to trigger image-release, then babysits image-release, chart-release, and test CI until all complete.
---

## Release process for doctorlib-navigator

Follow these steps in order. Do not skip steps.

### Step 1 — Determine the new version

Ask the user for the new version number if not provided (e.g. `0.4.0`). The corresponding git tag will be `v<version>`.

Check the current version:
```bash
grep '^version:' charts/doctorlib-navigator/Chart.yaml
git tag --sort=-v:refname | head -3
```

### Step 2 — Bump Chart.yaml

Update both `version` and `appVersion` in `charts/doctorlib-navigator/Chart.yaml` to the new version. The file must look like:

```yaml
version: <new-version>
appVersion: "<new-version>"
```

### Step 3 — Commit and push the version bump + tag

```bash
git add charts/doctorlib-navigator/Chart.yaml
git commit -m "chore: bump chart and appVersion to <new-version>"
git push origin master
git tag v<new-version>
git push origin v<new-version>
```

Pushing both simultaneously triggers:
- `image-release.yml` — fires on the semver tag, builds and pushes image to ghcr.io
- `chart-release.yml` — fires on Chart.yaml change on master, runs helm-docs, pushes OCI chart
- `test.yml` — fires on master push

### Step 4 — Babysit CI

Poll every 3 minutes until all three workflows complete:

```bash
gh run list --repo jo-hoe/doctorlib-navigator --limit 8
```

For any failed run fetch logs:
```bash
gh run view <id> --log-failed
```

Expected completion order: test (~1 min) → image-release (~2 min) → chart-release (~1 min, runs in parallel with image-release).

If chart-release fails with `fatal: invalid reference: origin/gh-pages`, the gh-pages branch is missing — this repo uses OCI push, not gh-pages, so this should not happen with the current workflow.

If image-release fails, do not proceed — the chart references this image version.

### Step 5 — Confirm

Report the final status of all three workflows and confirm:
- Image available at: `ghcr.io/jo-hoe/doctorlib-navigator:v<new-version>`
- Chart available at: `oci://ghcr.io/jo-hoe/doctorlib-navigator` version `<new-version>`
