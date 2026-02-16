#!/usr/bin/env python3
"""
Autonomous multi-agent orchestration over GitHub Issues.

Design goals:
- No external Python dependencies.
- Durable coordination across multiple machines without git-state conflicts.
- Lease-based claiming + heartbeats + retry/dead-letter handling.
- Pluggable per-agent execution commands (Codex by default).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
AUTONOMY_DIR = REPO_ROOT / ".tasks" / "autonomy"
RUNTIME_DIR = AUTONOMY_DIR / "runtime"
LOGS_DIR = RUNTIME_DIR / "logs"
PROMPTS_DIR = RUNTIME_DIR / "prompts"
CONFIG_PATH = AUTONOMY_DIR / "config.json"
LOCAL_CONFIG_PATH = AUTONOMY_DIR / "local.json"

META_RE = re.compile(r"<!-- AUTONOMY_META:(\{.*?\}) -->", re.DOTALL)
UNSUPPORTED_SEARCH_FLAG_RE = re.compile(r"unexpected argument ['\"]--search['\"]", re.IGNORECASE)

STATE_TO_LABEL = {
    "queued": "autonomy:queued",
    "running": "autonomy:running",
    "blocked": "autonomy:blocked",
    "done": "autonomy:done",
    "dead": "autonomy:dead",
}
ALL_STATE_LABELS = set(STATE_TO_LABEL.values())

REQUIRED_LABELS: Dict[str, Tuple[str, str]] = {
    "autonomy:job": ("1f6feb", "Top-level autonomous job issue"),
    "autonomy:task": ("0e8a16", "Runnable autonomous task"),
    "autonomy:queued": ("d4c5f9", "Task is queued"),
    "autonomy:running": ("fbca04", "Task is currently running"),
    "autonomy:blocked": ("d93f0b", "Task is blocked"),
    "autonomy:done": ("0e8a16", "Task completed"),
    "autonomy:dead": ("5319e7", "Task exhausted retries"),
    "priority:p1": ("b60205", "Highest priority"),
    "priority:p2": ("d93f0b", "High priority"),
    "priority:p3": ("fbca04", "Normal priority"),
    "agent:salomon": ("0052cc", "Assigned to Salomon"),
    "agent:stormforge": ("0e8a16", "Assigned to Stormforge"),
    "agent:kari": ("6f42c1", "Assigned to Kari"),
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "repo": "stormforge1/trisolaris",
    "poll_seconds": 45,
    "poll_jitter_seconds": 12,
    "lease_seconds": 900,
    "heartbeat_seconds": 120,
    "max_attempts": 3,
    "agent_timeout_seconds": 1800,
    "api_timeout_seconds": 30,
    "api_retry_attempts": 5,
    "agents": {
        "salomon": {
            "runner": "codex",
            "model": "",
            "extra_args": [],
            "search": True,
        },
        "stormforge": {
            "runner": "codex",
            "model": "",
            "extra_args": [],
            "search": True,
        },
        "kari": {
            "runner": "codex",
            "model": "",
            "extra_args": [],
            "search": True,
        },
    },
}

_CODEX_SEARCH_FLAG_SUPPORTED: Optional[bool] = None


@dataclass
class ExecResult:
    returncode: int
    timed_out: bool
    log_file: Path
    output_file: Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_ts(ts: Optional[datetime] = None) -> str:
    value = ts or utc_now()
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ensure_dirs() -> None:
    AUTONOMY_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_config() -> Dict[str, Any]:
    cfg = deep_merge(DEFAULT_CONFIG, load_json_file(CONFIG_PATH))
    cfg = deep_merge(cfg, load_json_file(LOCAL_CONFIG_PATH))
    return cfg


def short_text(text: str, limit: int = 600) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def slugify(text: str, max_len: int = 36) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    if not cleaned:
        cleaned = "task"
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len].rstrip("-")


def extract_meta(body: str) -> Dict[str, Any]:
    match = META_RE.search(body or "")
    if not match:
        return {}
    raw = match.group(1).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return {}
    return {}


def inject_meta(body: str, meta: Dict[str, Any]) -> str:
    serialized = json.dumps(meta, separators=(",", ":"), sort_keys=True)
    marker = f"<!-- AUTONOMY_META:{serialized} -->"
    existing = body or ""
    if META_RE.search(existing):
        return META_RE.sub(marker, existing)
    stripped = existing.rstrip()
    if not stripped:
        return marker + "\n"
    return stripped + "\n\n" + marker + "\n"


def priority_label(priority: str) -> str:
    p = priority.strip().lower()
    if p.startswith("priority:"):
        return p
    if p.startswith("p"):
        return f"priority:{p}"
    return "priority:p2"


def task_state_label(state: str) -> str:
    if state not in STATE_TO_LABEL:
        raise ValueError(f"Unsupported task state: {state}")
    return STATE_TO_LABEL[state]


def transition_task_labels(existing: Iterable[str], *, owner: str, state: str) -> List[str]:
    labels = set(existing)
    labels = {label for label in labels if label not in ALL_STATE_LABELS and not label.startswith("agent:")}
    labels.add(task_state_label(state))
    labels.add(f"agent:{owner}")
    return sorted(labels)


def transition_job_labels(existing: Iterable[str], *, state: str) -> List[str]:
    labels = set(existing)
    labels = {label for label in labels if label not in ALL_STATE_LABELS}
    labels.add(task_state_label(state))
    labels.add("autonomy:job")
    return sorted(labels)


def get_token() -> str:
    env_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env_token:
        return env_token
    proc = subprocess.run(["gh", "auth", "token"], text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("Unable to get GitHub token. Run: gh auth login")
    token = proc.stdout.strip()
    if not token:
        raise RuntimeError("Empty GitHub token from gh auth token")
    return token


def codex_exec_supports_search_flag() -> bool:
    global _CODEX_SEARCH_FLAG_SUPPORTED
    if _CODEX_SEARCH_FLAG_SUPPORTED is not None:
        return _CODEX_SEARCH_FLAG_SUPPORTED

    try:
        proc = subprocess.run(
            ["codex", "exec", "--help"],
            text=True,
            capture_output=True,
            timeout=15,
        )
        help_text = f"{proc.stdout}\n{proc.stderr}"
        _CODEX_SEARCH_FLAG_SUPPORTED = "--search" in help_text
    except Exception:
        _CODEX_SEARCH_FLAG_SUPPORTED = False

    return _CODEX_SEARCH_FLAG_SUPPORTED


class GitHubClient:
    def __init__(self, repo: str, *, timeout_seconds: int = 30, retry_attempts: int = 5) -> None:
        self.repo = repo
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.base = "https://api.github.com"
        self.token = get_token()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        query = ""
        if params:
            query = "?" + urlparse.urlencode(params, doseq=True)
        url = f"{self.base}{path}{query}"
        payload: Optional[bytes] = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        backoff = 1.5
        for attempt in range(1, self.retry_attempts + 1):
            req = urlrequest.Request(url, data=payload, method=method, headers=headers)
            try:
                with urlrequest.urlopen(req, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                    if not raw:
                        return {}
                    return json.loads(raw)
            except urlerror.HTTPError as exc:
                body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                retryable = exc.code in {408, 429, 500, 502, 503, 504}
                rate_limited = exc.code == 403 and "rate limit" in body_text.lower()
                if (retryable or rate_limited) and attempt < self.retry_attempts:
                    sleep_for = min(30.0, backoff + random.uniform(0.0, 0.8))
                    time.sleep(sleep_for)
                    backoff *= 2.0
                    continue
                raise RuntimeError(f"GitHub API {method} {path} failed ({exc.code}): {body_text}") from exc
            except urlerror.URLError as exc:
                if attempt < self.retry_attempts:
                    sleep_for = min(30.0, backoff + random.uniform(0.0, 0.8))
                    time.sleep(sleep_for)
                    backoff *= 2.0
                    continue
                raise RuntimeError(f"GitHub API {method} {path} network error: {exc}") from exc

        raise RuntimeError(f"GitHub API {method} {path} failed after retries")

    def list_labels(self) -> List[Dict[str, Any]]:
        return self._request("GET", f"/repos/{self.repo}/labels", params={"per_page": 100})

    def create_label(self, name: str, color: str, description: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/repos/{self.repo}/labels",
            body={"name": name, "color": color, "description": description},
        )

    def create_issue(self, *, title: str, body: str, labels: Sequence[str]) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/repos/{self.repo}/issues",
            body={"title": title, "body": body, "labels": list(labels)},
        )

    def update_issue(self, issue_number: int, **updates: Any) -> Dict[str, Any]:
        return self._request("PATCH", f"/repos/{self.repo}/issues/{issue_number}", body=updates)

    def get_issue(self, issue_number: int) -> Dict[str, Any]:
        return self._request("GET", f"/repos/{self.repo}/issues/{issue_number}")

    def create_comment(self, issue_number: int, comment_body: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/repos/{self.repo}/issues/{issue_number}/comments",
            body={"body": comment_body},
        )

    def list_issues(self, *, state: str = "open", labels: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        all_items: List[Dict[str, Any]] = []
        page = 1
        while True:
            params: Dict[str, Any] = {"state": state, "per_page": 100, "page": page}
            if labels:
                params["labels"] = ",".join(labels)
            items = self._request("GET", f"/repos/{self.repo}/issues", params=params)
            if not isinstance(items, list):
                raise RuntimeError("Unexpected response for list_issues")
            filtered = [item for item in items if "pull_request" not in item]
            all_items.extend(filtered)
            if len(items) < 100:
                break
            page += 1
        return all_items


def ensure_default_files() -> None:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")


def ensure_labels(client: GitHubClient) -> None:
    existing = {entry["name"] for entry in client.list_labels()}
    for name, (color, description) in REQUIRED_LABELS.items():
        if name in existing:
            continue
        client.create_label(name=name, color=color, description=description)


def build_job_body(spec: Dict[str, Any], *, creator: str) -> str:
    brief = spec.get("brief", "").strip()
    lines = ["# Autonomous Job", "", f"Creator: `{creator}`"]
    if brief:
        lines += ["", "## Brief", brief]
    lines += [
        "",
        "## Execution",
        "- Subtasks are tracked as separate `autonomy:task` issues.",
        "- Workers claim tasks via lease and heartbeat.",
    ]
    meta = {
        "type": "job",
        "status": "running",
        "creator": creator,
        "created_at": iso_ts(),
        "updated_at": iso_ts(),
    }
    return inject_meta("\n".join(lines), meta)


def build_task_body(
    *,
    job_number: int,
    owner: str,
    title: str,
    objective: str,
    deliverables: Sequence[str],
    depends_on: Sequence[int],
    task_id: str,
    branch: str,
    priority: str,
    max_attempts: int,
    next_owner: Optional[str],
) -> str:
    dep_lines = [f"- #{number}" for number in depends_on] or ["- none"]
    deliv_lines = [f"- `{path}`" for path in deliverables] or ["- none specified"]

    body = "\n".join(
        [
            "# Autonomous Task",
            "",
            f"Task ID: `{task_id}`",
            f"Parent Job: #{job_number}",
            f"Owner: `{owner}`",
            f"Priority: `{priority}`",
            f"Branch: `{branch}`",
            "",
            "## Objective",
            objective.strip() or title.strip(),
            "",
            "## Deliverables",
            *deliv_lines,
            "",
            "## Dependencies",
            *dep_lines,
            "",
            "## Notes",
            "- Worker should commit and open a PR against `main`.",
            "- Worker should post concise summary in issue comments.",
        ]
    )

    meta = {
        "type": "task",
        "task_id": task_id,
        "job_issue": job_number,
        "owner": owner,
        "status": "queued",
        "attempt": 0,
        "max_attempts": max_attempts,
        "lease_until": None,
        "worker": None,
        "created_at": iso_ts(),
        "updated_at": iso_ts(),
        "deliverables": list(deliverables),
        "depends_on": list(depends_on),
        "next_owner": next_owner,
        "branch": branch,
    }
    return inject_meta(body, meta)


def parse_spec(path: Path) -> Dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("Job spec must be a JSON object")
    if not spec.get("title"):
        raise ValueError("Job spec requires 'title'")
    tasks = spec.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Job spec requires non-empty 'tasks' array")
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise ValueError(f"Task {index} must be an object")
        if not task.get("owner"):
            raise ValueError(f"Task {index} missing owner")
        if not task.get("title"):
            raise ValueError(f"Task {index} missing title")
    return spec


def submit_job(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    spec_path = Path(args.spec).resolve()
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")
    spec = parse_spec(spec_path)
    creator = args.creator
    priority = priority_label(spec.get("priority", args.priority))

    # Validate owners/dependency shapes before any API mutation.
    for index, task_spec in enumerate(spec["tasks"], start=1):
        owner = str(task_spec.get("owner", "")).strip().lower()
        if owner not in cfg["agents"]:
            raise ValueError(f"Unknown owner '{owner}' in task {index}")
        raw_depends = task_spec.get("depends_on", [])
        if not isinstance(raw_depends, list):
            raise ValueError(f"Task {index}: depends_on must be a list")
        for dep_index in raw_depends:
            if not isinstance(dep_index, int):
                raise ValueError(f"Task {index}: depends_on entries must be task indices (int)")
            if dep_index >= index:
                raise ValueError(f"Task {index}: depends_on can only reference earlier tasks")
        next_owner = task_spec.get("next_owner")
        if next_owner is not None:
            next_owner_norm = str(next_owner).strip().lower()
            if next_owner_norm not in cfg["agents"]:
                raise ValueError(f"Task {index}: unknown next_owner '{next_owner_norm}'")

    client = GitHubClient(
        cfg["repo"],
        timeout_seconds=int(cfg["api_timeout_seconds"]),
        retry_attempts=int(cfg["api_retry_attempts"]),
    )

    ensure_labels(client)

    job_issue = client.create_issue(
        title=f"[AUTONOMY JOB] {spec['title']}",
        body=build_job_body(spec, creator=creator),
        labels=["autonomy:job", "autonomy:running", priority],
    )
    job_number = int(job_issue["number"])

    issue_numbers_by_index: Dict[int, int] = {}
    created: List[Tuple[int, str, str]] = []

    for index, task_spec in enumerate(spec["tasks"], start=1):
        owner = task_spec["owner"].strip().lower()
        if owner not in cfg["agents"]:
            raise ValueError(f"Unknown owner '{owner}' in task {index}")

        raw_depends = task_spec.get("depends_on", [])
        if not isinstance(raw_depends, list):
            raise ValueError(f"Task {index}: depends_on must be a list")
        depends_on: List[int] = []
        for dep_index in raw_depends:
            if not isinstance(dep_index, int):
                raise ValueError(f"Task {index}: depends_on entries must be task indices (int)")
            if dep_index >= index:
                raise ValueError(f"Task {index}: depends_on can only reference earlier tasks")
            if dep_index not in issue_numbers_by_index:
                raise ValueError(f"Task {index}: depends_on references unknown task index {dep_index}")
            depends_on.append(issue_numbers_by_index[dep_index])

        title = task_spec["title"].strip()
        objective = str(task_spec.get("objective", title))
        deliverables = task_spec.get("deliverables", [])
        if not isinstance(deliverables, list):
            raise ValueError(f"Task {index}: deliverables must be a list")
        deliverables_clean = [str(item).strip() for item in deliverables if str(item).strip()]

        next_owner = task_spec.get("next_owner")
        if next_owner is not None:
            next_owner = str(next_owner).strip().lower()
            if next_owner not in cfg["agents"]:
                raise ValueError(f"Task {index}: unknown next_owner '{next_owner}'")

        task_id = f"T-GH-PENDING-{index:02d}"
        branch = f"autonomy/{owner}-{slugify(title)}"

        body = build_task_body(
            job_number=job_number,
            owner=owner,
            title=title,
            objective=objective,
            deliverables=deliverables_clean,
            depends_on=depends_on,
            task_id=task_id,
            branch=branch,
            priority=priority,
            max_attempts=int(task_spec.get("max_attempts", cfg["max_attempts"])),
            next_owner=next_owner,
        )

        task_issue = client.create_issue(
            title=f"[AUTONOMY TASK] {title}",
            body=body,
            labels=["autonomy:task", "autonomy:queued", f"agent:{owner}", priority],
        )
        task_number = int(task_issue["number"])

        # Backfill stable IDs now that the issue exists.
        task_id = f"T-GH-{task_number}"
        branch = f"autonomy/{owner}-gh-{task_number}-{slugify(title)}"
        created_meta = extract_meta(task_issue.get("body", ""))
        created_meta["task_id"] = task_id
        created_meta["branch"] = branch
        created_meta["updated_at"] = iso_ts()

        patched_body = inject_meta(task_issue.get("body", ""), created_meta)
        patched_body = patched_body.replace("`T-GH-PENDING-{:02d}`".format(index), f"`{task_id}`")
        patched_body = patched_body.replace(
            f"`autonomy/{owner}-{slugify(title)}`",
            f"`{branch}`",
        )
        client.update_issue(task_number, body=patched_body)

        issue_numbers_by_index[index] = task_number
        created.append((task_number, owner, title))

        client.create_comment(
            task_number,
            "\n".join(
                [
                    f"[autonomy] Task created for `{owner}` from job #{job_number}.",
                    f"Task ID: `{task_id}`",
                    f"Branch hint: `{branch}`",
                ]
            ),
        )

    task_lines = [f"- #{number} `{owner}`: {title}" for number, owner, title in created]
    client.create_comment(
        job_number,
        "\n".join(
            [
                "[autonomy] Subtasks created:",
                *task_lines,
            ]
        ),
    )

    print(f"Created job #{job_number} with {len(created)} tasks")
    for number, owner, title in created:
        print(f"- #{number} [{owner}] {title}")
    return 0


def dependencies_met(client: GitHubClient, issue_meta: Dict[str, Any]) -> Tuple[bool, List[int]]:
    missing: List[int] = []
    for number in issue_meta.get("depends_on", []):
        dep = client.get_issue(int(number))
        labels = {label["name"] for label in dep.get("labels", [])}
        if dep.get("state") != "closed" or "autonomy:done" not in labels:
            missing.append(int(number))
    return (len(missing) == 0, missing)


def task_prompt(issue: Dict[str, Any], meta: Dict[str, Any], *, agent: str, repo: str) -> str:
    task_id = meta.get("task_id", f"T-GH-{issue['number']}")
    branch = meta.get("branch", f"autonomy/{agent}-gh-{issue['number']}")
    deliverables = meta.get("deliverables", [])
    deliverable_lines = "\n".join([f"- {path}" for path in deliverables]) or "- follow task issue details"

    return "\n".join(
        [
            f"You are agent '{agent}'.",
            f"Repository: {repo}",
            f"Issue: #{issue['number']} ({issue['title']})",
            f"Task ID: {task_id}",
            "",
            "Goal:",
            issue.get("body", "").strip(),
            "",
            "Execution requirements:",
            f"1) Create/use branch: {branch}",
            "2) Implement the task fully in the local repository.",
            "3) Run relevant checks/tests for changed files.",
            "4) Ensure these deliverables are present:",
            deliverable_lines,
            "5) Commit with message starting with the Task ID (for example: 'T-GH-123: ...').",
            "6) Push the branch and open a PR to main referencing this issue number.",
            "7) In your final response, include: summary, changed files, validation commands/results, PR link.",
            "",
            "Be concise and execution-focused.",
        ]
    )


def build_runner_command(
    *,
    agent: str,
    cfg: Dict[str, Any],
    prompt_file: Path,
    output_file: Path,
    issue_number: int,
) -> Tuple[List[str], Optional[str]]:
    agent_cfg = cfg["agents"][agent]
    runner = str(agent_cfg.get("runner", "codex")).lower()

    if runner == "codex":
        cmd: List[str] = [
            "codex",
            "exec",
            "--full-auto",
            "--cd",
            str(REPO_ROOT),
            "-o",
            str(output_file),
        ]
        if agent_cfg.get("search", False):
            if codex_exec_supports_search_flag():
                cmd.append("--search")
            else:
                print(
                    "[autonomy] configured search=true but local codex exec does not support --search; continuing without it.",
                    file=sys.stderr,
                )
        model = str(agent_cfg.get("model", "")).strip()
        if model:
            cmd.extend(["--model", model])
        extra_args = agent_cfg.get("extra_args", [])
        if not isinstance(extra_args, list):
            raise ValueError(f"agents.{agent}.extra_args must be a list")
        cmd.extend([str(item) for item in extra_args])
        cmd.append("-")
        return cmd, prompt_file.read_text(encoding="utf-8")

    if runner == "shell":
        template = str(agent_cfg.get("command", "")).strip()
        if not template:
            raise ValueError(f"agents.{agent}.command is required for shell runner")
        mapping = {
            "repo_root": str(REPO_ROOT),
            "prompt_file": str(prompt_file),
            "output_file": str(output_file),
            "issue_number": str(issue_number),
            "agent": agent,
        }
        expanded = template.format(**mapping)
        return ["bash", "-lc", expanded], None

    if runner == "noop":
        return ["bash", "-lc", "echo '[autonomy] noop runner success'"], None

    raise ValueError(f"Unsupported runner '{runner}' for agent '{agent}'")


def renew_lease(
    client: GitHubClient,
    issue_number: int,
    *,
    expected_owner: str,
    lease_seconds: int,
) -> None:
    issue = client.get_issue(issue_number)
    meta = extract_meta(issue.get("body", ""))
    if meta.get("type") != "task":
        return
    if meta.get("status") != "running":
        return
    if meta.get("owner") != expected_owner:
        return

    meta["lease_until"] = iso_ts(utc_now() + timedelta(seconds=lease_seconds))
    meta["updated_at"] = iso_ts()
    new_body = inject_meta(issue.get("body", ""), meta)
    client.update_issue(issue_number, body=new_body)


def run_process_with_heartbeat(
    *,
    client: GitHubClient,
    issue_number: int,
    owner: str,
    cmd: List[str],
    prompt_stdin: Optional[str],
    cfg: Dict[str, Any],
    log_file: Path,
    output_file: Path,
) -> ExecResult:
    timeout_seconds = int(cfg["agent_timeout_seconds"])
    heartbeat_seconds = int(cfg["heartbeat_seconds"])
    lease_seconds = int(cfg["lease_seconds"])

    start = time.monotonic()
    deadline = start + timeout_seconds
    next_heartbeat = start + heartbeat_seconds

    with log_file.open("w", encoding="utf-8") as lf:
        lf.write(f"$ {' '.join(shlex.quote(part) for part in cmd)}\n")
        lf.flush()

        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdin=subprocess.PIPE if prompt_stdin is not None else None,
            stdout=lf,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if prompt_stdin is not None and proc.stdin is not None:
            proc.stdin.write(prompt_stdin)
            proc.stdin.close()

        timed_out = False

        while True:
            rc = proc.poll()
            now_mono = time.monotonic()
            if rc is not None:
                return ExecResult(returncode=rc, timed_out=timed_out, log_file=log_file, output_file=output_file)

            if now_mono >= deadline:
                timed_out = True
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                rc2 = proc.wait()
                return ExecResult(returncode=rc2, timed_out=timed_out, log_file=log_file, output_file=output_file)

            if now_mono >= next_heartbeat:
                renew_lease(client, issue_number, expected_owner=owner, lease_seconds=lease_seconds)
                next_heartbeat = now_mono + heartbeat_seconds

            time.sleep(2)


def task_comment_summary(*, prefix: str, message: str, output_file: Path, log_file: Path) -> str:
    output_text = ""
    if output_file.exists():
        output_text = short_text(output_file.read_text(encoding="utf-8", errors="replace"), limit=1000)
    body_lines = [f"[autonomy] {prefix}", "", message]
    if output_text:
        body_lines += ["", "Summary:", output_text]
    body_lines += ["", f"Log: `{log_file}`"]
    return "\n".join(body_lines)


def mark_task_done_or_handoff(
    client: GitHubClient,
    issue: Dict[str, Any],
    meta: Dict[str, Any],
    *,
    output_file: Path,
    log_file: Path,
) -> None:
    issue_number = int(issue["number"])
    owner = str(meta["owner"])
    next_owner = meta.get("next_owner")

    if next_owner:
        next_owner = str(next_owner).strip().lower()
        meta["owner"] = next_owner
        meta["status"] = "queued"
        meta["lease_until"] = None
        meta["worker"] = None
        meta["updated_at"] = iso_ts()
        labels = transition_task_labels((label["name"] for label in issue.get("labels", [])), owner=next_owner, state="queued")
        new_body = inject_meta(issue.get("body", ""), meta)
        client.update_issue(issue_number, body=new_body, labels=labels)
        client.create_comment(
            issue_number,
            task_comment_summary(
                prefix=f"completed by `{owner}` and handed off to `{next_owner}`",
                message="Task execution succeeded and has been queued for the next owner.",
                output_file=output_file,
                log_file=log_file,
            ),
        )
        return

    meta["status"] = "done"
    meta["lease_until"] = None
    meta["worker"] = None
    meta["completed_at"] = iso_ts()
    meta["updated_at"] = iso_ts()

    labels = transition_task_labels((label["name"] for label in issue.get("labels", [])), owner=owner, state="done")
    new_body = inject_meta(issue.get("body", ""), meta)
    client.update_issue(issue_number, body=new_body, labels=labels, state="closed")
    client.create_comment(
        issue_number,
        task_comment_summary(
            prefix=f"completed by `{owner}`",
            message="Task execution succeeded and issue has been closed.",
            output_file=output_file,
            log_file=log_file,
        ),
    )


def handle_task_failure(
    client: GitHubClient,
    issue: Dict[str, Any],
    meta: Dict[str, Any],
    *,
    returncode: int,
    timed_out: bool,
    log_file: Path,
) -> None:
    issue_number = int(issue["number"])
    owner = str(meta["owner"])
    attempt = int(meta.get("attempt", 0))
    max_attempts = int(meta.get("max_attempts", 3))

    failure_reason = f"timeout after worker limit" if timed_out else f"runner exit code {returncode}"
    known_fix_hint = ""
    if log_file.exists():
        log_text = log_file.read_text(encoding="utf-8", errors="replace")
        if UNSUPPORTED_SEARCH_FLAG_RE.search(log_text):
            known_fix_hint = (
                " Detected unsupported `--search` flag in local codex CLI;"
                " worker should auto-disable this flag now."
            )
            failure_reason += " (unsupported --search flag)"
    meta["last_error"] = failure_reason
    meta["updated_at"] = iso_ts()
    meta["lease_until"] = None
    meta["worker"] = None

    if attempt < max_attempts:
        meta["status"] = "queued"
        labels = transition_task_labels((label["name"] for label in issue.get("labels", [])), owner=owner, state="queued")
        new_body = inject_meta(issue.get("body", ""), meta)
        client.update_issue(issue_number, body=new_body, labels=labels)
        client.create_comment(
            issue_number,
            "\n".join(
                [
                    f"[autonomy] task run failed for `{owner}` ({failure_reason}).",
                    f"Attempt `{attempt}` of `{max_attempts}`. Re-queued.",
                    known_fix_hint.strip(),
                    f"Log: `{log_file}`",
                ]
            ),
        )
        return

    meta["status"] = "dead"
    labels = transition_task_labels((label["name"] for label in issue.get("labels", [])), owner=owner, state="dead")
    new_body = inject_meta(issue.get("body", ""), meta)
    client.update_issue(issue_number, body=new_body, labels=labels)
    client.create_comment(
        issue_number,
        "\n".join(
            [
                f"[autonomy] task exhausted retries for `{owner}` ({failure_reason}).",
                f"Attempt `{attempt}` of `{max_attempts}`. Marked dead-letter.",
                known_fix_hint.strip(),
                f"Log: `{log_file}`",
            ]
        ),
    )


def refresh_job_state(client: GitHubClient, job_issue_number: int) -> None:
    open_tasks = client.list_issues(state="open", labels=["autonomy:task"])
    closed_tasks = client.list_issues(state="closed", labels=["autonomy:task"])
    tasks = open_tasks + closed_tasks

    related: List[Dict[str, Any]] = []
    for issue in tasks:
        meta = extract_meta(issue.get("body", ""))
        if int(meta.get("job_issue", -1)) == int(job_issue_number):
            related.append(issue)

    if not related:
        return

    has_dead_or_blocked = False
    all_done = True
    for issue in related:
        labels = {label["name"] for label in issue.get("labels", [])}
        meta = extract_meta(issue.get("body", ""))
        status = str(meta.get("status", "")).lower()
        if status in {"dead", "blocked"} or "autonomy:dead" in labels or "autonomy:blocked" in labels:
            has_dead_or_blocked = True
        if "autonomy:done" not in labels or issue.get("state") != "closed":
            all_done = False

    job = client.get_issue(job_issue_number)
    job_labels = [label["name"] for label in job.get("labels", [])]
    job_meta = extract_meta(job.get("body", ""))
    if job_meta.get("type") != "job":
        job_meta["type"] = "job"
    job_meta["updated_at"] = iso_ts()

    if all_done:
        job_meta["status"] = "done"
        labels = transition_job_labels(job_labels, state="done")
        client.update_issue(job_issue_number, body=inject_meta(job.get("body", ""), job_meta), labels=labels, state="closed")
        return

    if has_dead_or_blocked:
        job_meta["status"] = "blocked"
        labels = transition_job_labels(job_labels, state="blocked")
        client.update_issue(job_issue_number, body=inject_meta(job.get("body", ""), job_meta), labels=labels)
        return

    job_meta["status"] = "running"
    labels = transition_job_labels(job_labels, state="running")
    client.update_issue(job_issue_number, body=inject_meta(job.get("body", ""), job_meta), labels=labels)


def claim_next_task_for_agent(client: GitHubClient, cfg: Dict[str, Any], agent: str) -> Optional[Dict[str, Any]]:
    queued = client.list_issues(state="open", labels=["autonomy:task", f"agent:{agent}", "autonomy:queued"])
    if not queued:
        return None

    # Oldest first by issue number for deterministic scheduling.
    queued_sorted = sorted(queued, key=lambda issue: int(issue["number"]))

    for issue in queued_sorted:
        number = int(issue["number"])
        fresh = client.get_issue(number)
        labels = {label["name"] for label in fresh.get("labels", [])}
        if "autonomy:queued" not in labels:
            continue

        meta = extract_meta(fresh.get("body", ""))
        if meta.get("type") != "task":
            continue
        owner = str(meta.get("owner", "")).strip().lower()
        if owner != agent:
            continue

        deps_ok, _missing = dependencies_met(client, meta)
        if not deps_ok:
            continue

        attempt = int(meta.get("attempt", 0)) + 1
        max_attempts = int(meta.get("max_attempts", cfg["max_attempts"]))
        if attempt > max_attempts:
            continue

        worker = f"{agent}@{socket.gethostname()}:{os.getpid()}"
        meta["status"] = "running"
        meta["attempt"] = attempt
        meta["worker"] = worker
        meta["lease_until"] = iso_ts(utc_now() + timedelta(seconds=int(cfg["lease_seconds"])))
        meta["updated_at"] = iso_ts()

        updated_body = inject_meta(fresh.get("body", ""), meta)
        new_labels = transition_task_labels(labels, owner=agent, state="running")
        updated_issue = client.update_issue(number, body=updated_body, labels=new_labels)

        client.create_comment(
            number,
            "\n".join(
                [
                    f"[autonomy] claimed by `{worker}`",
                    f"Attempt: `{attempt}` / `{max_attempts}`",
                    f"Lease until: `{meta['lease_until']}`",
                ]
            ),
        )
        return updated_issue

    return None


def execute_claimed_task(client: GitHubClient, cfg: Dict[str, Any], issue: Dict[str, Any], agent: str) -> None:
    meta = extract_meta(issue.get("body", ""))
    issue_number = int(issue["number"])
    task_id = str(meta.get("task_id", f"T-GH-{issue_number}"))

    prompt_file = PROMPTS_DIR / f"{task_id}-{agent}.md"
    log_file = LOGS_DIR / f"{task_id}-{agent}-{int(time.time())}.log"
    output_file = LOGS_DIR / f"{task_id}-{agent}-last-message.txt"

    prompt_text = task_prompt(issue, meta, agent=agent, repo=cfg["repo"])
    prompt_file.write_text(prompt_text, encoding="utf-8")

    cmd, prompt_stdin = build_runner_command(
        agent=agent,
        cfg=cfg,
        prompt_file=prompt_file,
        output_file=output_file,
        issue_number=issue_number,
    )

    result = run_process_with_heartbeat(
        client=client,
        issue_number=issue_number,
        owner=agent,
        cmd=cmd,
        prompt_stdin=prompt_stdin,
        cfg=cfg,
        log_file=log_file,
        output_file=output_file,
    )

    latest = client.get_issue(issue_number)
    latest_meta = extract_meta(latest.get("body", ""))
    if latest_meta.get("status") != "running":
        client.create_comment(
            issue_number,
            "[autonomy] task finished locally but remote state is no longer running; skipping final transition.",
        )
        return

    if result.returncode == 0 and not result.timed_out:
        mark_task_done_or_handoff(
            client,
            latest,
            latest_meta,
            output_file=result.output_file,
            log_file=result.log_file,
        )
    else:
        handle_task_failure(
            client,
            latest,
            latest_meta,
            returncode=result.returncode,
            timed_out=result.timed_out,
            log_file=result.log_file,
        )

    job_issue_number = int(latest_meta.get("job_issue", 0))
    if job_issue_number > 0:
        refresh_job_state(client, job_issue_number)


def run_agent_once(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    agent = args.agent.strip().lower()
    if agent not in cfg["agents"]:
        raise ValueError(f"Unknown agent: {agent}")

    client = GitHubClient(
        cfg["repo"],
        timeout_seconds=int(cfg["api_timeout_seconds"]),
        retry_attempts=int(cfg["api_retry_attempts"]),
    )

    task = claim_next_task_for_agent(client, cfg, agent)
    if task is None:
        print(f"No runnable queued task for {agent}")
        return 0

    execute_claimed_task(client, cfg, task, agent)
    print(f"Processed task #{task['number']} for {agent}")
    return 0


def run_agent_loop(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    while True:
        run_agent_once(args, cfg)
        if not args.loop:
            return 0
        base = int(cfg["poll_seconds"])
        jitter = int(cfg.get("poll_jitter_seconds", 0))
        delay = base + random.randint(0, max(0, jitter))
        time.sleep(delay)


def requeue_stale(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    client = GitHubClient(
        cfg["repo"],
        timeout_seconds=int(cfg["api_timeout_seconds"]),
        retry_attempts=int(cfg["api_retry_attempts"]),
    )
    running = client.list_issues(state="open", labels=["autonomy:task", "autonomy:running"])
    now = utc_now()
    touched = 0

    for issue in running:
        meta = extract_meta(issue.get("body", ""))
        if meta.get("type") != "task":
            continue
        owner = str(meta.get("owner", "")).strip().lower()
        if args.agent and owner != args.agent:
            continue

        lease_until_raw = meta.get("lease_until")
        if not lease_until_raw:
            continue
        try:
            lease_until = parse_iso_ts(str(lease_until_raw))
        except ValueError:
            lease_until = now - timedelta(seconds=1)

        if lease_until > now:
            continue

        attempt = int(meta.get("attempt", 0))
        max_attempts = int(meta.get("max_attempts", cfg["max_attempts"]))
        issue_number = int(issue["number"])
        labels = {label["name"] for label in issue.get("labels", [])}

        if attempt < max_attempts:
            meta["status"] = "queued"
            meta["lease_until"] = None
            meta["worker"] = None
            meta["updated_at"] = iso_ts()
            new_body = inject_meta(issue.get("body", ""), meta)
            new_labels = transition_task_labels(labels, owner=owner, state="queued")
            client.update_issue(issue_number, body=new_body, labels=new_labels)
            client.create_comment(
                issue_number,
                "[autonomy] lease expired with no heartbeat; task returned to queued state.",
            )
        else:
            meta["status"] = "dead"
            meta["lease_until"] = None
            meta["worker"] = None
            meta["updated_at"] = iso_ts()
            new_body = inject_meta(issue.get("body", ""), meta)
            new_labels = transition_task_labels(labels, owner=owner, state="dead")
            client.update_issue(issue_number, body=new_body, labels=new_labels)
            client.create_comment(
                issue_number,
                "[autonomy] lease expired and max attempts reached; marked dead-letter.",
            )

        job_issue_number = int(meta.get("job_issue", 0))
        if job_issue_number > 0:
            refresh_job_state(client, job_issue_number)
        touched += 1

    print(f"Requeued/updated stale tasks: {touched}")
    return 0


def status(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    client = GitHubClient(
        cfg["repo"],
        timeout_seconds=int(cfg["api_timeout_seconds"]),
        retry_attempts=int(cfg["api_retry_attempts"]),
    )

    open_tasks = client.list_issues(state="open", labels=["autonomy:task"])
    closed_tasks = client.list_issues(state="closed", labels=["autonomy:task"])

    counts = {"queued": 0, "running": 0, "blocked": 0, "dead": 0, "done": 0}
    by_agent: Dict[str, int] = {agent: 0 for agent in cfg["agents"]}

    for issue in open_tasks + closed_tasks:
        meta = extract_meta(issue.get("body", ""))
        state = str(meta.get("status", "")).lower()
        if state in counts:
            counts[state] += 1
        owner = str(meta.get("owner", "")).lower()
        if owner in by_agent:
            by_agent[owner] += 1

    print(f"Repo: {cfg['repo']}")
    print("Task counts:")
    for state in ["queued", "running", "blocked", "dead", "done"]:
        print(f"- {state}: {counts[state]}")
    print("By owner:")
    for owner, count in by_agent.items():
        print(f"- {owner}: {count}")
    return 0


def sync_board(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    client = GitHubClient(
        cfg["repo"],
        timeout_seconds=int(cfg["api_timeout_seconds"]),
        retry_attempts=int(cfg["api_retry_attempts"]),
    )

    open_tasks = client.list_issues(state="open", labels=["autonomy:task"])
    closed_done = client.list_issues(state="closed", labels=["autonomy:task", "autonomy:done"])

    in_progress_rows: List[str] = []
    for issue in sorted(open_tasks, key=lambda i: int(i["number"])):
        meta = extract_meta(issue.get("body", ""))
        if meta.get("type") != "task":
            continue
        status_val = str(meta.get("status", "queued"))
        task_id = str(meta.get("task_id", f"T-GH-{issue['number']}"))
        owner = str(meta.get("owner", "-"))
        branch = str(meta.get("branch", "-"))
        started = str(meta.get("created_at", issue.get("created_at", "")))[:10]
        blockers = "none"
        if status_val in {"blocked", "dead"}:
            blockers = short_text(str(meta.get("last_error", status_val)), limit=80)
        title = short_text(issue.get("title", ""), limit=80)
        in_progress_rows.append(f"| {task_id} | {title} | {owner} | {branch} | {started} | {blockers} |")

    done_rows: List[str] = []
    for issue in sorted(closed_done, key=lambda i: int(i["number"])):
        meta = extract_meta(issue.get("body", ""))
        if meta.get("type") != "task":
            continue
        task_id = str(meta.get("task_id", f"T-GH-{issue['number']}"))
        owner = str(meta.get("owner", "-"))
        closed = str(issue.get("closed_at", ""))[:10]
        title = short_text(issue.get("title", ""), limit=80)
        pr_ref = f"Issue #{issue['number']}"
        notes = f"{cfg['repo']}#{issue['number']}"
        done_rows.append(f"| {task_id} | {title} | {owner} | {closed} | {pr_ref} | {notes} |")

    in_progress_md = [
        "# In Progress",
        "",
        "| Task ID | Title | Owner | Branch | Started (YYYY-MM-DD) | Blockers |",
        "|---|---|---|---|---|---|",
    ]
    if in_progress_rows:
        in_progress_md.extend(in_progress_rows)
    else:
        in_progress_md.append("| - | - | - | - | - | - |")

    done_md = [
        "# Done",
        "",
        "| Task ID | Title | Owner | Closed (YYYY-MM-DD) | PR/Commit | Notes |",
        "|---|---|---|---|---|---|",
    ]
    if done_rows:
        done_md.extend(done_rows)
    else:
        done_md.append("| - | - | - | - | - | - |")

    (REPO_ROOT / ".tasks" / "in-progress.md").write_text("\n".join(in_progress_md) + "\n", encoding="utf-8")
    (REPO_ROOT / ".tasks" / "done.md").write_text("\n".join(done_md) + "\n", encoding="utf-8")

    print("Updated .tasks/in-progress.md and .tasks/done.md from GitHub autonomy issues")
    return 0


def supervisor(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    while True:
        requeue_stale(args, cfg)
        if args.sync_board:
            sync_board(args, cfg)
        if not args.loop:
            return 0
        base = int(cfg["poll_seconds"])
        jitter = int(cfg.get("poll_jitter_seconds", 0))
        delay = base + random.randint(0, max(0, jitter))
        time.sleep(delay)


def bootstrap(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    ensure_default_files()
    client = GitHubClient(
        cfg["repo"],
        timeout_seconds=int(cfg["api_timeout_seconds"]),
        retry_attempts=int(cfg["api_retry_attempts"]),
    )
    ensure_labels(client)
    print("Autonomy bootstrap completed")
    print(f"- repo: {cfg['repo']}")
    print(f"- config: {CONFIG_PATH}")
    if LOCAL_CONFIG_PATH.exists():
        print(f"- local override: {LOCAL_CONFIG_PATH}")
    else:
        print(f"- optional local override: {LOCAL_CONFIG_PATH}")
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autonomous multi-agent orchestration over GitHub Issues")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap", help="Create default files and GitHub labels")

    submit_p = sub.add_parser("submit", help="Submit a job from a JSON spec")
    submit_p.add_argument("--spec", required=True, help="Path to JSON job spec")
    submit_p.add_argument("--creator", default="odin", help="Job creator identity")
    submit_p.add_argument("--priority", default="P2", help="Fallback priority if missing in spec")

    agent_p = sub.add_parser("run-agent", help="Claim and execute tasks for one agent")
    agent_p.add_argument("--agent", required=True, choices=["salomon", "stormforge", "kari"])
    agent_p.add_argument("--loop", action="store_true", help="Run forever")

    stale_p = sub.add_parser("requeue-stale", help="Requeue expired running tasks")
    stale_p.add_argument("--agent", choices=["salomon", "stormforge", "kari"], default=None)

    sub.add_parser("status", help="Print autonomy queue summary")
    sub.add_parser("sync-board", help="Sync markdown task board from GitHub issue state")

    sup_p = sub.add_parser("supervisor", help="Supervisor loop: stale recovery (+ optional board sync)")
    sup_p.add_argument("--loop", action="store_true", help="Run forever")
    sup_p.add_argument("--sync-board", action="store_true", help="Also sync markdown board each cycle")
    sup_p.add_argument("--agent", choices=["salomon", "stormforge", "kari"], default=None)

    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ensure_default_files()
    args = parse_args(argv)
    cfg = load_config()

    command = args.command
    if command == "bootstrap":
        return bootstrap(args, cfg)
    if command == "submit":
        return submit_job(args, cfg)
    if command == "run-agent":
        return run_agent_loop(args, cfg)
    if command == "requeue-stale":
        return requeue_stale(args, cfg)
    if command == "status":
        return status(args, cfg)
    if command == "sync-board":
        return sync_board(args, cfg)
    if command == "supervisor":
        return supervisor(args, cfg)

    raise RuntimeError(f"Unknown command: {command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
