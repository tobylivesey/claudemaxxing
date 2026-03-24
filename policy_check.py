"""
policy_check.py — monitors Anthropic's rate-limit documentation for changes.

On each run it fetches the monitored URLs, stores a fingerprint + snapshot,
and alerts when content has materially changed since the last check.
"""

import hashlib
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from analyze import load_config

SCRIPT_DIR = Path(__file__).parent
STATE_PATH = SCRIPT_DIR / "policy_state.json"

# Sentences containing these words are extracted for fingerprinting
RELEVANT_KEYWORDS = [
    # Claude rate-limit terms
    "token", "limit", "window", "weekly", "hourly", "rate",
    "pro", "max", "reset", "cap", "usage", "5-hour", "5 hour",
    # OffSec / OSCP syllabus terms
    "syllabus", "exam", "pen-200", "pen200", "oscp", "module",
    "updated", "removed", "added", "objective", "topic",
]


# ── State persistence ─────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"checks": {}}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def fetch_text(url: str, timeout: int = 15) -> str | None:
    """Fetch URL and return plain text (strips HTML tags)."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "claudemaxxing-policy-checker/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"  [policy_check] fetch failed for {url}: {e}")
        return None


def extract_relevant_sections(text: str) -> str:
    """Pull out sentences/phrases containing rate-limit keywords."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    relevant  = [s.strip() for s in sentences if any(kw in s.lower() for kw in RELEVANT_KEYWORDS)]
    return " | ".join(relevant)


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── Core check ────────────────────────────────────────────────────────────────

class PolicyChange:
    def __init__(self, url: str, old_fp: str, new_fp: str, old_snippet: str, new_snippet: str):
        self.url         = url
        self.old_fp      = old_fp
        self.new_fp      = new_fp
        self.old_snippet = old_snippet
        self.new_snippet = new_snippet

    def __repr__(self) -> str:
        return (
            f"\n  URL: {self.url}\n"
            f"  fingerprint: {self.old_fp} -> {self.new_fp}\n"
            f"  BEFORE relevant sections:\n    {self.old_snippet[:400]}\n"
            f"  AFTER  relevant sections:\n    {self.new_snippet[:400]}\n"
        )


def run_policy_check(force: bool = False) -> list[PolicyChange]:
    """
    Fetch monitored URLs, compare against saved state.
    Returns list of PolicyChange objects (empty = no changes).
    """
    config = load_config()
    pc     = config.get("policy_check", {})

    if not pc.get("enabled", True):
        print("  [policy_check] disabled in config.json")
        return []

    interval_days = pc.get("check_interval_days", 14)
    urls          = pc.get("urls_to_monitor", [])
    state         = load_state()
    checks        = state.setdefault("checks", {})
    now           = datetime.now(timezone.utc)   # captured once for the whole run
    now_str       = now.isoformat()
    changes: list[PolicyChange] = []

    for url in urls:
        url_state    = checks.get(url, {})
        last_checked = url_state.get("last_checked")

        if not force and last_checked:
            last_dt  = datetime.fromisoformat(last_checked)
            age_days = (now - last_dt).days
            if age_days < interval_days:
                print(f"  [policy_check] skipping {url} (checked {age_days}d ago)")
                continue

        print(f"  [policy_check] fetching {url}")
        text = fetch_text(url)
        if text is None:
            continue

        relevant = extract_relevant_sections(text)
        new_fp   = fingerprint(relevant)
        old_fp   = url_state.get("fingerprint")
        old_snip = url_state.get("relevant_snippet", "")

        if old_fp and old_fp != new_fp:
            changes.append(PolicyChange(url, old_fp, new_fp, old_snip, relevant))

        checks[url] = {
            "last_checked":     now_str,
            "fingerprint":      new_fp,
            "relevant_snippet": relevant[:2000],
        }

    state["last_run"] = now_str
    save_state(state)

    return changes


def print_policy_report(changes: list[PolicyChange]) -> None:
    if not changes:
        print("  [policy_check] no changes detected in monitored pages.")
        return

    print(f"\n{'!'*52}")
    print(f"  POLICY CHANGE DETECTED -- {len(changes)} page(s) changed")
    print(f"  Review changes below and update config.json + analyze.py")
    print(f"  if rate limits have changed.")
    print(f"{'!'*52}")
    for c in changes:
        print(c)
    print(
        "\n  Action items:\n"
        "  1. Visit the URLs above and read the updated limits\n"
        "  2. Update WINDOW_TOKEN_LIMIT / EXPECTED_ACTIVE_WINDOWS_PER_WEEK in analyze.py\n"
        "  3. Update the 'limits' block in config.json\n"
        "  4. Update '_last_verified' date in config.json\n"
    )


if __name__ == "__main__":
    import sys
    changes = run_policy_check(force="--force" in sys.argv)
    print_policy_report(changes)
