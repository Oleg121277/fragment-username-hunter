#!/usr/bin/env python3
"""Deploy a static file to GitHub Pages.

Usage:
    python deploy_to_github_pages.py <file_path> [repo_name]

Creates/updates a GitHub repo, pushes the file as index.html,
enables GitHub Pages, and prints the live URL.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run command, return CompletedProcess."""
    print(f"  → {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def gh_path() -> str:
    """Find gh CLI executable."""
    candidates = [
        r"C:\Program Files\GitHub CLI\gh.exe",
        r"C:\Program Files (x86)\GitHub CLI\gh.exe",
        shutil.which("gh"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    raise FileNotFoundError("gh CLI not found. Install: winget install --id GitHub.cli -e")


def get_gh_user(gh: str) -> str:
    r = run([gh, "api", "user", "--jq", ".login"])
    return r.stdout.strip()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: deploy_to_github_pages.py <file_path> [repo_name]")
        sys.exit(1)

    src_file = Path(sys.argv[1]).resolve()
    if not src_file.exists():
        print(f"Error: file not found: {src_file}")
        sys.exit(1)

    repo_name = sys.argv[2] if len(sys.argv) > 2 else f"page-{src_file.stem}"
    gh = gh_path()
    user = get_gh_user(gh)

    print(f"📦 Deploying {src_file.name} → {user}/{repo_name}")

    # Create temp dir with index.html
    tmp = Path(tempfile.mkdtemp(prefix="ghpages_"))
    dst = tmp / "index.html"
    shutil.copy2(src_file, dst)
    print(f"  📄 Copied to {dst}")

    # Init git repo
    run(["git", "init"], cwd=str(tmp))
    run(["git", "config", "user.email", f"{user}@users.noreply.github.com"], cwd=str(tmp))
    run(["git", "config", "user.name", user], cwd=str(tmp))
    run(["git", "add", "."], cwd=str(tmp))
    run(["git", "commit", "-m", f"Deploy {src_file.name}"], cwd=str(tmp))

    # Create or update remote repo
    create_r = run(
        [gh, "repo", "create", repo_name, "--public", "--source", str(tmp), "--push", "--silent"],
        check=False,
    )
    if create_r.returncode != 0:
        # Repo may already exist — add remote and force push
        print("  ⚠️  Repo exists, updating...")
        # Ensure clean remote state: remove stale origin before re-adding
        run(["git", "remote", "remove", "origin"], cwd=str(tmp), check=False)
        run(["git", "remote", "add", "origin", f"https://github.com/{user}/{repo_name}.git"], cwd=str(tmp))
        run(["git", "push", "--force", "origin", "HEAD"], cwd=str(tmp))

    # Enable GitHub Pages
    branch_r = run(["git", "symbolic-ref", "--short", "HEAD"], cwd=str(tmp))
    branch = branch_r.stdout.strip() or "master"

    pages_payload = json.dumps({
        "build_type": "legacy",
        "source": {"branch": branch, "path": "/"},
    })
    enable_r = run(
        [gh, "api", f"repos/{user}/{repo_name}/pages", "-X", "POST", "--input", "-"],
        cwd=str(tmp),
        check=False,
    )
    if enable_r.returncode != 0:
        # Might already be enabled — try PUT
        run(
            [gh, "api", f"repos/{user}/{repo_name}/pages", "-X", "PUT",
             "-f", f"build_type=legacy", "-f", f"source[branch]={branch}", "-f", "source[path]=/"],
            cwd=str(tmp),
            check=False,
        )

    # Poll for build completion
    url = f"https://{user}.github.io/{repo_name}/"
    print("  ⏳ Waiting for Pages build...")
    for i in range(6):
        time.sleep(15)
        status_r = run(
            [gh, "api", f"repos/{user}/{repo_name}/pages", "--jq", ".status"],
            check=False,
        )
        status = status_r.stdout.strip()
        if status == "built":
            break
        print(f"     Status: {status} ({(i+1)*15}s)")

    # Cleanup
    shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n✅ Deployed!\n   🔗 {url}\n   📁 Repo: https://github.com/{user}/{repo_name}")


if __name__ == "__main__":
    main()
