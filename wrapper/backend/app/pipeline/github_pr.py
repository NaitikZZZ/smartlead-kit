"""Commits a run's 3 output files to a new branch and opens a PR, via the
GitHub REST API (Git Data API for an atomic multi-file commit) rather than
shelling out to `gh` - the backend is a shared hosted instance, not every
user's authenticated machine."""
import base64
from pathlib import Path

import requests

from .. import config

API = "https://api.github.com"


def _headers():
    token = config.require("GITHUB_TOKEN", config.GITHUB_TOKEN)
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def open_output_pr(run_id: str, run_label: str, output_files: dict[str, str], stats_summary: str) -> str:
    repo = config.require("GITHUB_REPO", config.GITHUB_REPO)
    base_branch = config.GITHUB_BASE_BRANCH
    headers = _headers()

    ref = requests.get(f"{API}/repos/{repo}/git/ref/heads/{base_branch}", headers=headers, timeout=15)
    ref.raise_for_status()
    base_sha = ref.json()["object"]["sha"]

    base_commit = requests.get(f"{API}/repos/{repo}/git/commits/{base_sha}", headers=headers, timeout=15)
    base_commit.raise_for_status()
    base_tree_sha = base_commit.json()["tree"]["sha"]

    tree_entries = []
    for filename, local_path in output_files.items():
        content = Path(local_path).read_bytes()
        blob = requests.post(
            f"{API}/repos/{repo}/git/blobs", headers=headers, timeout=30,
            json={"content": base64.b64encode(content).decode(), "encoding": "base64"},
        )
        blob.raise_for_status()
        tree_entries.append({
            "path": f"wrapper_outputs/{run_id}/{filename}",
            "mode": "100644", "type": "blob", "sha": blob.json()["sha"],
        })

    tree = requests.post(
        f"{API}/repos/{repo}/git/trees", headers=headers, timeout=15,
        json={"base_tree": base_tree_sha, "tree": tree_entries},
    )
    tree.raise_for_status()

    commit = requests.post(
        f"{API}/repos/{repo}/git/commits", headers=headers, timeout=15,
        json={
            "message": f"ABM wrapper run {run_id}: {run_label or 'enrichment output'}",
            "tree": tree.json()["sha"], "parents": [base_sha],
        },
    )
    commit.raise_for_status()
    commit_sha = commit.json()["sha"]

    branch_name = f"abm-wrapper/{run_id}"
    create_ref = requests.post(
        f"{API}/repos/{repo}/git/refs", headers=headers, timeout=15,
        json={"ref": f"refs/heads/{branch_name}", "sha": commit_sha},
    )
    create_ref.raise_for_status()

    pr = requests.post(
        f"{API}/repos/{repo}/pulls", headers=headers, timeout=15,
        json={
            "title": f"ABM enrichment output: {run_label or run_id}",
            "head": branch_name, "base": base_branch,
            "body": f"Automated output from the ABM wrapper.\n\nRun ID: `{run_id}`\n\n{stats_summary}",
        },
    )
    pr.raise_for_status()
    return pr.json()["html_url"]
