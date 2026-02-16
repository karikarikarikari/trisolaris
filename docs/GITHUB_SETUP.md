# GitHub Setup (Multi-Account)

Use this guide to run Odin (`welttowelt`) and Salomon (`salomon-shdow`) on the same machine safely.

## Account Map
- Odin (human): `welttowelt`
- Salomon (Codex): `salomon-shdow`
- Stormforge (Codex): `stormforge1`
- Kari (Claude): `karikarikarikari`

## 1) Log in both accounts with `gh`

```bash
gh auth login --hostname github.com --git-protocol ssh --skip-ssh-key --web
```

Run that once for each account (switch browser session as needed).

Check:

```bash
gh auth status
```

Switch active account:

```bash
gh auth switch --hostname github.com --user welttowelt
gh auth switch --hostname github.com --user salomon-shdow
```

## 2) Create dedicated SSH key for Salomon

```bash
ssh-keygen -t ed25519 -C "salomon-shdow" -f ~/.ssh/id_ed25519_salomon
```

Add SSH alias in `~/.ssh/config`:

```sshconfig
Host github-salomon
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_salomon
  IdentitiesOnly yes
```

## 3) Upload Salomon SSH key to GitHub account

If needed, add key-management scope once:

```bash
gh auth switch --hostname github.com --user salomon-shdow
gh auth refresh --hostname github.com --scopes admin:public_key
```

Upload key:

```bash
gh ssh-key add ~/.ssh/id_ed25519_salomon.pub --title "salomon-shdow-<machine-name>"
```

Verify SSH identity:

```bash
ssh -T git@github-salomon
```

Expected output starts with: `Hi salomon-shdow!`

## 4) Point Trisolaris repo to Salomon SSH identity

```bash
cd ~/Documents/Trisolaris
git remote set-url origin git@github-salomon:stormforge1/trisolaris.git
git remote -v
```

## 5) Verify API account and git SSH identity match

```bash
gh auth status
ssh -T git@github-salomon
```

- `gh` active account should be `salomon-shdow`
- SSH greeting should be `Hi salomon-shdow!`

## 6) Ensure write access on target repos

From repo owner account, grant write:

```bash
# On stormforge1/trisolaris (run as stormforge1)
gh api -X PUT /repos/stormforge1/trisolaris/collaborators/salomon-shdow -f permission=push

# On welttowelt/yggdrasil-runner (run as welttowelt)
gh api -X PUT /repos/welttowelt/yggdrasil-runner/collaborators/salomon-shdow -f permission=push
```

Accept invitations as `salomon-shdow`:

```bash
gh auth switch --hostname github.com --user salomon-shdow
gh api /user/repository_invitations
gh api -X PATCH /user/repository_invitations/<INVITE_ID>
```

Verify permission:

```bash
gh repo view stormforge1/trisolaris --json nameWithOwner,viewerPermission
gh repo view welttowelt/yggdrasil-runner --json nameWithOwner,viewerPermission
```

## 7) Optional: set git author identity in this repo

```bash
cd ~/Documents/Trisolaris
git config user.name "salomon-shdow"
git config user.email "salomon-shdow@users.noreply.github.com"
```

## Troubleshooting
- `gh` account switch fails intermittently:
  - retry `gh auth switch --hostname github.com --user <user>`
- SSH shows wrong user:
  - check remote uses `github-salomon` alias
  - check `~/.ssh/config` alias block exists
  - rerun `ssh -T git@github-salomon`
- No write access:
  - invite exists but not accepted, or wrong owner account granted access
