# Main Branch Protection Status (`stormforge1/trisolaris`)

Date: 2026-02-16
Task: `T-GH-19`
Issue: `#19`
Owner: `stormforge`
Branch target: `main`

## Objective
Ensure `main` does **not** require pull request reviews, while keeping the hard rule intact.

## Verification Attempt (Stormforge workspace session)

### Commands executed
```bash
gh auth status
gh api repos/stormforge1/trisolaris/branches/main/protection --jq '{required_pull_request_reviews: .required_pull_request_reviews, enforce_admins: .enforce_admins.enabled, required_status_checks: .required_status_checks.strict, restrictions: .restrictions}'
```

### Observed results
- `gh auth status` reported invalid tokens for configured accounts (`stormforge1`, `welttowelt`).
- `gh api .../protection` failed with connection/auth failure in this session.

## Local execution constraints observed

### Commands executed
```bash
git fetch origin --prune
git checkout -B autonomy/stormforge-gh-19-update-main-branch-protection-to-rem
```

### Observed results
- `git fetch` failed: cannot open `.git/FETCH_HEAD` (operation not permitted).
- `git checkout -B ...` failed: cannot create `.git/index.lock` (operation not permitted).

## Required action when run on the real Stormforge machine/account
Run from a shell with:
1. valid `gh` auth for `stormforge1`
2. writable `.git` metadata
3. network access to `api.github.com`

Then execute:

```bash
git checkout -B autonomy/stormforge-gh-19-update-main-branch-protection-to-rem

gh api \
  --method PATCH \
  repos/stormforge1/trisolaris/branches/main/protection \
  -f required_status_checks='{"strict":true,"contexts":[]}' \
  -f enforce_admins=true \
  -f required_pull_request_reviews= \
  -f restrictions=

# verify

gh api repos/stormforge1/trisolaris/branches/main/protection \
  --jq '{required_pull_request_reviews: .required_pull_request_reviews, enforce_admins: .enforce_admins.enabled, required_status_checks: .required_status_checks}'
```

Expected verification condition:
- `required_pull_request_reviews` is `null`.

## Notes
This file records the rerun attempt from the current workspace and the exact operational blockers. No remote protection change was applied in this sandboxed session.
