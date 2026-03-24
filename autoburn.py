"""
autoburn.py — invokes `claude -p` for each enabled burn task.
Called by burn.sh (cron) on a homelab or burn.ps1 (Task Scheduler) on Windows.

Utilisation strategy (in order of preference):
  1. claude.ai API (usage_api.py) — real server-side data, works across all
     machines sharing the same Pro account. Requires CLAUDE_ORG_ID and
     CLAUDE_SESSION_COOKIE env vars. See usage_api.py for setup instructions.
  2. Rate-limit-as-signal fallback — if the API is unavailable or unconfigured,
     tasks are attempted directly and a rate-limit response stops the cycle.

Exit codes:
  0  — completed normally (tasks ran, rate-limited, or outside allowed hours)
  1  — hard error (config missing, claude not found, etc.)
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from analyze import load_config
from usage_api import SessionExpiredError, fetch_usage

SCRIPT_DIR = Path(__file__).parent
TASKS_PATH = SCRIPT_DIR / "tasks.json"
LOG_PATH   = SCRIPT_DIR / "burn.log"

RATE_LIMIT_MARKERS = [
    "rate limit", "429", "usage limit", "too many requests",
    "overloaded", "quota exceeded",
]


# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

log = logging.getLogger(__name__)


# ── Allowed hours ─────────────────────────────────────────────────────────────

def _load_hour_range() -> tuple[int, int] | None:
    """Returns (start, end) from config, or None if all hours are allowed."""
    try:
        cfg = load_config().get("autoburn", {})
        start = cfg.get("allowed_hours_start")
        end   = cfg.get("allowed_hours_end")
        if start is None or end is None:
            return None
        return (int(start), int(end))
    except Exception:
        return None


def _in_allowed_hours(hour: int) -> bool:
    hr = _load_hour_range()
    if hr is None:
        return True  # no restriction configured
    start, end = hr
    if start == end == 0:
        return True  # explicit all-day setting
    if start > end:  # wraps midnight, e.g. 22-8
        return hour >= start or hour < end
    return start <= hour < end


# ── Tasks ─────────────────────────────────────────────────────────────────────

def load_tasks() -> list[dict]:
    if not TASKS_PATH.exists():
        log.warning("tasks.json not found — nothing to burn")
        return []
    with open(TASKS_PATH) as f:
        data = json.load(f)
    tasks = [t for t in data.get("tasks", []) if t.get("enabled", False)]
    log.info(f"Loaded {len(tasks)} enabled task(s) from tasks.json")
    return tasks


# ── Claude invocation ─────────────────────────────────────────────────────────

def _is_rate_limited(output: str) -> bool:
    lower = output.lower()
    return any(m in lower for m in RATE_LIMIT_MARKERS)


def run_claude_task(task: dict) -> str:
    """
    Invoke `claude -p` for the task.
    Returns: 'ok' | 'rate_limited' | 'error'
    """
    name        = task["name"]
    prompt      = task["prompt"]
    working_dir = Path(task.get("working_dir", ".")).expanduser()

    if not working_dir.exists():
        log.error(f"  Working dir not found: {working_dir}")
        return "error"

    log.info(f"  Running task: {name}")
    log.info(f"  Dir: {working_dir}")

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
        )
        combined = (result.stdout or "") + (result.stderr or "")

        if _is_rate_limited(combined):
            log.warning(f"  Rate limited by server — 5-hour window full")
            return "rate_limited"

        if result.returncode != 0:
            log.warning(f"  Task exited {result.returncode}: {name}")
            if combined.strip():
                log.warning(f"  Output: {combined.strip()[:400]}")
            return "error"

        log.info(f"  Task completed: {name}")
        if result.stdout.strip():
            preview = result.stdout.strip()[:1000]
            log.info(f"  Output:\n{preview}")
        return "ok"

    except subprocess.TimeoutExpired:
        log.error(f"  Task timed out after 1 hour: {name}")
        return "error"
    except FileNotFoundError:
        log.error("  `claude` not found in PATH — is Claude Code installed?")
        return "error"


# ── Utilisation check ─────────────────────────────────────────────────────────

BURN_THRESHOLD_PCT = 80.0   # don't run tasks if window is already above this %


def _check_utilisation() -> tuple[bool, str]:
    """
    Returns (should_run, reason).
    Tries the claude.ai API first; falls back to always-run (rate-limit-as-signal).
    """
    try:
        usage = fetch_usage()
    except SessionExpiredError as e:
        log.warning(f"  {e}")
        log.warning("  Update CLAUDE_SESSION_COOKIE — falling back to rate-limit mode")
        return True, "api-unavailable (session expired)"

    if usage is None:
        return True, "api-unavailable (no credentials — using rate-limit-as-signal)"

    resets = usage.five_hour_resets_at.astimezone(timezone.utc)
    log.info(
        f"Usage (API): window {usage.five_hour_pct:.0f}%  "
        f"7-day {usage.seven_day_pct:.0f}%  "
        f"window resets {resets.strftime('%H:%M UTC')}"
    )

    if usage.five_hour_pct >= BURN_THRESHOLD_PCT:
        return False, f"window {usage.five_hour_pct:.0f}% full (>= {BURN_THRESHOLD_PCT:.0f}% threshold)"

    return True, f"window {usage.five_hour_pct:.0f}% used — burn needed"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    setup_logging()
    log.info("=== autoburn start ===")

    local_hour = datetime.now().hour
    if not _in_allowed_hours(local_hour):
        hr = _load_hour_range()
        log.info(f"Outside allowed hours ({hr[0]:02d}:00-{hr[1]:02d}:00) — skipping")
        return 0

    should_run, reason = _check_utilisation()
    if not should_run:
        log.info(f"Skipping: {reason}")
        return 0

    log.info(f"Burn triggered: {reason}")

    tasks = load_tasks()
    if not tasks:
        return 0

    ran = 0
    for task in tasks:
        status = run_claude_task(task)
        if status == "ok":
            ran += 1
        elif status == "rate_limited":
            log.info("Window full — stopping burn for this cycle")
            break
        # "error": already logged, continue to next task

    log.info(f"=== autoburn complete: {ran} task(s) ran ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
