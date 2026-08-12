---
name: release
description: Release a new version of doctorlib-navigator. Supports two release types — full (new image + chart) and chart-only (chart bump, existing image). Run in foreground (run_in_background: false) so step progress is visible in real time.
allowedTools:
  - Read
  - Edit
  - Bash(git *)
  - Bash(gh *)
  - Bash(helm *)
  - Bash(grep *)
---

## Release process for doctorlib-navigator

Follow these steps in order. Do not skip steps. After each step, report completion with a one-line status so the user can track progress.

### Step 1 — Determine version and release type

Report: `[Step 1/5] Determining version and release type...`

If not provided in the prompt, check the current versions:
```bash
grep -E '^version:|^appVersion:' charts/doctorlib-navigator/Chart.yaml
git tag --sort=-v:refname | head -3
```

Ask the user (or infer from context) whether this is:
- **Full release** — new image + new chart (code changes). Bumps both `version` and `appVersion`. Pushes a new semver tag to trigger `image-release.yml`.
- **Chart-only release** — chart changes only, image unchanged. Bumps only `version`, keeps `appVersion` at the current value. No new tag pushed.

Report: `[Step 1/5] ✓ Release type: <full|chart-only>, chart version: <new-version>, appVersion: <app-version>`

### Step 2 — Bump Chart.yaml

Report: `[Step 2/5] Bumping Chart.yaml...`

**Full release:** update both fields:
```yaml
version: <new-version>
appVersion: "<new-version>"
```

**Chart-only release:** update only `version`, leave `appVersion` unchanged:
```yaml
version: <new-version>
appVersion: "<current-app-version>"   # unchanged
```

Report: `[Step 2/5] ✓ Chart.yaml updated`

### Step 3 — Commit, push, and (for full releases) tag

Report: `[Step 3/5] Committing and pushing...`

```bash
git add charts/doctorlib-navigator/Chart.yaml
git commit -m "chore: bump chart and appVersion to <new-version>"
git push origin main
```

**Full release only** — also push the semver tag to trigger image-release:
```bash
git tag v<new-version>
git push origin v<new-version>
```

If push fails due to remote changes, rebase first:
```bash
git fetch origin && git rebase origin/main
```
Then re-push (and re-tag if needed).

Report: `[Step 3/5] ✓ Pushed main` (and `+ tag v<new-version>` for full releases)

### Step 4 — Babysit CI

Report: `[Step 4/5] Waiting for CI (timeout: 10 minutes)...`

Poll every 30 seconds, up to 20 times. On each poll:
```bash
gh run list --repo jo-hoe/doctorlib-navigator --limit 8
```

**Full release** — track all three:
- `test` — triggered by main push
- `Release Image` — triggered by the semver tag
- `Release Chart` — triggered by Chart.yaml change on main

**Chart-only release** — track only two:
- `test` — triggered by main push
- `Release Chart` — triggered by Chart.yaml change on main

Report each poll as: `[Step 4/5] Poll <n>/20 — test: <status>, image: <status|n/a>, chart: <status>`

Stop as soon as all tracked workflows show `completed`. If any shows `failure`, fetch logs immediately:
```bash
gh run view <id> --log-failed
```
Then report the failure and stop.

If 20 polls pass without completion: `[Step 4/5] ✗ Timeout after 10 minutes` and stop.

Report: `[Step 4/5] ✓ All workflows completed successfully`

### Step 5 — Verify and confirm

Report: `[Step 5/5] Verifying published artifacts...`

Always verify the chart:
```bash
helm show chart oci://ghcr.io/jo-hoe/charts/doctorlib-navigator --version <new-version>
```

For full releases also verify the image tag via the workflow success (image API requires read:packages scope which may not be available).

If chart verification fails, report the error and stop.

Report: `[Step 5/5] ✓ Release complete`

Confirm:
- Chart: `oci://ghcr.io/jo-hoe/charts/doctorlib-navigator --version <new-version>`
- Image: `ghcr.io/jo-hoe/doctorlib-navigator:v<app-version>` (full release) or `unchanged at v<current-app-version>` (chart-only)
