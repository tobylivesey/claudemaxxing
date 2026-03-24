"""
vault_status.py — reads the cyberSecurityVault claude-review progress tracker
and prints a dashboard of review progress, recent sessions, gaps, and issues.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from analyze import load_config

def _vault_dir() -> Path:
    cfg = load_config()
    raw = cfg.get("vault", {}).get("dir", "")
    if not raw:
        return Path()
    return Path(raw).expanduser()

PROGRESS_REF = "claude-review:_claude-review/progress.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_progress() -> dict | None:
    """
    Read progress.json from the claude-review branch via `git show`,
    regardless of which branch is currently checked out in the working tree.
    Falls back to reading the file directly from disk if git fails.
    """
    vault_dir     = _vault_dir()
    progress_path = vault_dir / "_claude-review" / "progress.json"

    if not vault_dir.parts:
        return None

    # Strategy 1: git show (works on any branch)
    try:
        raw = subprocess.check_output(
            ["git", "show", PROGRESS_REF],
            cwd=str(vault_dir),
            stderr=subprocess.DEVNULL,
        )
        return json.loads(raw.decode("utf-8"))
    except Exception:
        pass

    # Strategy 2: direct file read (works when claude-review is checked out)
    try:
        if progress_path.exists():
            return json.loads(progress_path.read_bytes())
    except Exception:
        pass

    return None


def bar(pct: float, width: int = 28) -> str:
    filled = int(min(pct, 1.0) * width)
    return "#" * filled + "-" * (width - filled)


def vault_git_status() -> tuple[str, str]:
    """Returns (current_branch, last_commit_summary)."""
    vault_dir = _vault_dir()
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=vault_dir, text=True, stderr=subprocess.DEVNULL
        ).strip()
        log = subprocess.check_output(
            ["git", "log", "--oneline", "-1"],
            cwd=vault_dir, text=True, stderr=subprocess.DEVNULL
        ).strip()
        return branch, log
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", "unknown"


def recent_sessions(data: dict, n: int = 5) -> list[dict]:
    return data.get("sessions", [])[-n:]


# ── Report ────────────────────────────────────────────────────────────────────

def print_vault_status(full: bool = False) -> None:
    vault_dir = _vault_dir()
    data = load_progress()
    if data is None:
        print("  [vault] progress.json not found.")
        print(f"  Expected: {vault_dir / '_claude-review' / 'progress.json'}")
        print("  Run from PowerShell (not WSL) — vault paths are Windows-native.")
        return

    stats = data.get("stats", {})
    total  = stats.get("oscp_in_scope", stats.get("total_in_queue", 0))
    done   = stats.get("reviewed", 0)
    pct    = done / total if total else 0
    gaps   = stats.get("gaps_flagged", 0)
    links  = stats.get("links_added", 0)
    issues = stats.get("accuracy_flagged", 0)
    sessions_done = data.get("sessions_completed", 0)
    last_session  = data.get("last_session") or "never"

    branch, last_commit = vault_git_status()

    print(f"\n{'='*52}")
    print(f"  vault review -- OSCP progress")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*52}")

    print(f"\n  Overall progress")
    print(f"  {bar(pct)}  {pct*100:.1f}%")
    print(f"  {done} / {total} OSCP-priority notes reviewed")
    print(f"  Sessions completed : {sessions_done}")
    print(f"  Last session       : {last_session}")

    print(f"\n  Findings so far")
    print(f"  Gaps flagged    : {gaps}")
    print(f"  Links added     : {links}")
    print(f"  Accuracy issues : {issues}")

    print(f"\n  Vault git state")
    print(f"  Branch      : {branch}")
    print(f"  Last commit : {last_commit}")
    if branch == "main":
        print(f"  !! Not on claude-review — sessions must run on claude-review branch")

    if recent := recent_sessions(data):
        print(f"\n  Recent sessions")
        for s in reversed(recent):
            print(
                f"  {s.get('date','?')}  "
                f"{s.get('notes_reviewed',0)} notes  "
                f"{s.get('gaps_flagged',0)} gaps  "
                f"{s.get('links_added',0)} links  "
                f"{s.get('accuracy_flagged',0)} issues"
            )

    if full:
        _print_full_detail(data)

    # Next pending note
    queue = data.get("queue", [])
    pending = [e for e in queue if e.get("status") == "pending"]
    if pending:
        print(f"\n  Next note to review")
        print(f"  {pending[0]['path']}")
        print(f"  (priority {pending[0]['priority']}, {len(pending)} notes remaining)")

    print(f"{'='*52}\n")


def _print_full_detail(data: dict) -> None:
    """Printed with --vault-full: list all gaps and issues found so far."""
    gaps = data.get("gaps", [])
    if gaps:
        print(f"\n  All gaps identified ({len(gaps)})")
        for g in gaps:
            note = Path(g.get("path", "")).name
            missing = g.get("missing", [])
            print(f"  [{note}]")
            for m in missing:
                print(f"    - {m}")

    issues = data.get("issues", [])
    if issues:
        print(f"\n  All accuracy issues ({len(issues)})")
        for i in issues:
            note = Path(i.get("path", "")).name
            print(f"  [{note}] {i.get('reason', '')}")


def one_line_status() -> str:
    """Short string for embedding in run.py --status output."""
    data = load_progress()
    if data is None:
        return "vault: not initialised"
    stats = data.get("stats", {})
    total = stats.get("oscp_in_scope", 0)
    done  = stats.get("reviewed", 0)
    pct   = done / total * 100 if total else 0
    last  = data.get("last_session") or "never"
    return f"vault: {done}/{total} notes ({pct:.0f}%) | last session: {last}"


if __name__ == "__main__":
    import sys
    full = "--full" in sys.argv
    print_vault_status(full=full)
