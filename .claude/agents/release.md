---
name: release
description: Release a new version of doctorlib-navigator. Bumps Chart.yaml version+appVersion, pushes a semver tag to trigger image-release, then babysits image-release, chart-release, and test CI until all complete. Run in foreground (run_in_background: false) so step progress is visible in real time.
---

## Release process for doctorlib-navigator

Follow these steps in order. Do not skip steps. After each step, report completion with a one-line status so the user can track progress.

### Step 1 — Determine the new version

Report: `[Step 1/5] Determining version...`

If the version was provided in the prompt, use it. Otherwise check the current version and ask:
```bash
grep '^version:' charts/doctorlib-navigator/Chart.yaml
git tag --sort=-v:refname | head -3
```

Report: `[Step 1/5] ✓ Releasing version <new-version> (tag: v<new-version>)`

### Step 2 — Bump Chart.yaml

Report: `[Step 2/5] Bumping Chart.yaml...`

Update both `version` and `appVersion` in `charts/doctorlib-navigator/Chart.yaml`:

```yaml
version: <new-version>
appVersion: "<new-version>"
```

Report: `[Step 2/5] ✓ Chart.yaml updated`

### Step 3 — Commit, push, and tag

Report: `[Step 3/5] Committing, pushing, and tagging...`

```bash
git add charts/doctorlib-navigator/Chart.yaml
git commit -m "chore: bump chart and appVersion to <new-version>"
git push origin main
git tag v<new-version>
git push origin v<new-version>
```

If `git push origin main` fails due to remote changes, rebase first:
```bash
git fetch origin && git rebase origin/main
```
Then re-push.

Report: `[Step 3/5] ✓ Pushed main + tag v<new-version> — CI triggered`

### Step 4 — Babysit CI

Report: `[Step 4/5] Waiting for CI (timeout: 10 minutes)...`

Poll every 30 seconds, up to 20 times (10 minutes total). On each poll:
```bash
gh run list --repo jo-hoe/doctorlib-navigator --limit 8
```

Track these three workflows triggered by this release:
- `test` — triggered by the main push
- `Release Image` — triggered by the `v<new-version>` tag
- `Release Chart` — triggered by the Chart.yaml change on main

Report each poll as: `[Step 4/5] Poll <n>/20 — test: <status>, image: <status>, chart: <status>`

Stop polling as soon as all three show `completed`. If any shows `failure`, immediately fetch logs:
```bash
gh run view <id> --log-failed
```
Then report the failure and stop.

If 20 polls pass without all completing, report: `[Step 4/5] ✗ Timeout after 10 minutes — last status: test: <status>, image: <status>, chart: <status>` and stop.

Expected completion order: test (~1 min) → image-release (~2 min) → chart-release (~1 min).

Report: `[Step 4/5] ✓ All workflows completed successfully`

### Step 5 — Verify and confirm

Report: `[Step 5/5] Verifying published artifacts...`

Verify the image tag exists:
```bash
gh api /users/jo-hoe/packages/container/doctorlib-navigator/versions --jq '.[0].metadata.container.tags'
```

Verify the chart is pullable:
```bash
helm show chart oci://ghcr.io/jo-hoe/charts/doctorlib-navigator --version <new-version>
```

If either verification fails, report the error and stop.

Report: `[Step 5/5] ✓ Release complete`

Confirm:
- Image: `ghcr.io/jo-hoe/doctorlib-navigator:v<new-version>`
- Chart: `oci://ghcr.io/jo-hoe/charts/doctorlib-navigator --version <new-version>`
