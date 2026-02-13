# New Project Utilities

This repo contains small utilities for:
- generating new account names in the same style as `account_names_seed.txt`
- managing local (gitignored) secrets via `.env.local`
- cloning `welttowelt/yggdrasil-runner` once you have GitHub access

## Local secrets

Your real creds should live in `.env.local` (gitignored).

Start from:

- `.env.local.example`

## Generate names

```sh
python3 scripts/spin_up_names.py --count 40
```

Output:
- `generated_account_names_YYYY-MM-DD.txt`

## Check cartridge env

```sh
python3 scripts/check_cartridge_env.py
```

This prints the username and a masked password (never the full password).

## Clone yggdrasil-runner

If the GitHub repo is private, add a PAT (fine-grained token) to `.env.local`:

```dotenv
GITHUB_TOKEN=...
```

Then:

```sh
python3 scripts/clone_yggdrasil_runner.py
```

You can also point it at a different repo:

```sh
python3 scripts/clone_yggdrasil_runner.py --repo owner/name
```

## License

MIT -- see [LICENSE](LICENSE).
