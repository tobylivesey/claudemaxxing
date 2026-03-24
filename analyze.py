"""
analyze.py — reads all Claude Code session JSONL files and computes token burn rates.

Token counting for rate-limit purposes:
  effective_tokens = input_tokens + output_tokens

  cache_creation_input_tokens are stored separately — they are large but counted at reduced
  rates and do NOT appear to be what Anthropic tracks toward window/weekly caps.
  (stats-cache.json only records input+output, and those figures match documented limits.)
  cache_read_input_tokens are cheapest and excluded entirely.
"""

import json
import glob
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple


# ── Paths ─────────────────────────────────────────────────────────────────────

CLAUDE_DIR   = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
SCRIPT_DIR   = Path(__file__).parent
CONFIG_PATH  = SCRIPT_DIR / "config.json"


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Single source of truth for config loading — imported by other modules."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


# Pro plan limits — kept as module constants for fast access; also reflected in config.json.
# Update both if you change plan.
WINDOW_HOURS = 5
WINDOW_TOKEN_LIMIT = 44_000       # ~tokens per 5-hour window for Pro

# Weekly budget: Anthropic's "40-80 Sonnet hours" cap can't be reliably converted to
# input+output token counts (in practice ~1-10K tokens/hour, not theoretical maximums).
# We use a practical target: 10 well-used windows/week as a reasonable active-user goal.
EXPECTED_ACTIVE_WINDOWS_PER_WEEK = 10
WEEKLY_TOKEN_BUDGET = EXPECTED_ACTIVE_WINDOWS_PER_WEEK * WINDOW_TOKEN_LIMIT  # 440K

UNDERUTIL_THRESHOLD        = 0.5   # flag if window usage < 50% of limit
WEEKLY_UNDERUTIL_THRESHOLD = 0.25  # flag if rolling 7-day usage < 25% of expected weekly

# Sunday 21:00 local = "last night before the weekly window resets"
LAST_NIGHT_WEEKDAY = 6   # Sunday
LAST_NIGHT_HOUR    = 21


# ── Data loading ──────────────────────────────────────────────────────────────

class TokenEvent(NamedTuple):
    timestamp: datetime
    model: str
    input_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    output_tokens: int
    effective_tokens: int   # what counts toward window limits = input + output


def load_all_events() -> list[TokenEvent]:
    """Scan every session JSONL file under ~/.claude/projects/ and extract token events."""
    events: list[TokenEvent] = []
    pattern = str(PROJECTS_DIR / "**" / "*.jsonl")

    for path in glob.glob(pattern, recursive=True):
        # Skip subagent files to avoid double-counting
        if "subagents" in path:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if obj.get("type") != "assistant":
                        continue

                    msg   = obj.get("message", {})
                    usage = msg.get("usage")
                    if not usage:
                        continue

                    ts_raw = obj.get("timestamp")
                    if not ts_raw:
                        continue
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    except ValueError:
                        continue

                    inp = usage.get("input_tokens", 0)
                    cc  = usage.get("cache_creation_input_tokens", 0)
                    cr  = usage.get("cache_read_input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    eff = inp + out   # only input+output count toward window limits

                    events.append(TokenEvent(ts, msg.get("model", "unknown"), inp, cc, cr, out, eff))

        except (OSError, PermissionError):
            continue

    events.sort(key=lambda e: e.timestamp)
    return events


# ── Analysis ──────────────────────────────────────────────────────────────────

def _events_since(events: list[TokenEvent], cutoff: datetime):
    """Yield events at or after cutoff. Events must be sorted ascending."""
    for e in events:
        if e.timestamp >= cutoff:
            yield e


def tokens_in_window(events: list[TokenEvent], now: datetime, hours: int = WINDOW_HOURS) -> int:
    cutoff = now - timedelta(hours=hours)
    return sum(e.effective_tokens for e in _events_since(events, cutoff))


def tokens_in_week(events: list[TokenEvent], now: datetime) -> int:
    cutoff = now - timedelta(days=7)
    return sum(e.effective_tokens for e in _events_since(events, cutoff))


def daily_breakdown(events: list[TokenEvent], now: datetime, days: int = 30) -> dict[str, int]:
    """Returns {date_str: effective_tokens} for the last N days."""
    cutoff = now - timedelta(days=days)
    by_day: dict[str, int] = defaultdict(int)
    for e in _events_since(events, cutoff):
        by_day[e.timestamp.strftime("%Y-%m-%d")] += e.effective_tokens
    return dict(sorted(by_day.items()))


def windows_per_week_estimate(events: list[TokenEvent], now: datetime) -> float:
    """How many distinct 5-hour windows had any activity in the last 7 days."""
    cutoff    = now - timedelta(days=7)
    slot_size = WINDOW_HOURS * 3600
    slots = {
        int(e.timestamp.timestamp()) // slot_size
        for e in _events_since(events, cutoff)
    }
    return float(len(slots))


# ── Report ────────────────────────────────────────────────────────────────────

class BurnReport(NamedTuple):
    now: datetime
    window_tokens: int
    window_limit: int
    window_pct: float
    window_underutilized: bool
    weekly_tokens: int
    weekly_budget: int
    weekly_pct: float
    weekly_underutilized: bool
    active_windows_last_7d: float
    daily_breakdown: dict[str, int]
    last_event_ts: datetime | None


def build_report(events: list[TokenEvent] | None = None) -> BurnReport:
    if events is None:
        events = load_all_events()
    now = datetime.now(timezone.utc)

    win_tok  = tokens_in_window(events, now)
    win_pct  = win_tok / WINDOW_TOKEN_LIMIT

    wk_tok   = tokens_in_week(events, now)
    wk_pct   = wk_tok / WEEKLY_TOKEN_BUDGET

    active_w = windows_per_week_estimate(events, now)
    daily    = daily_breakdown(events, now)
    last_ts  = events[-1].timestamp if events else None

    return BurnReport(
        now=now,
        window_tokens=win_tok,
        window_limit=WINDOW_TOKEN_LIMIT,
        window_pct=win_pct,
        window_underutilized=(win_pct < UNDERUTIL_THRESHOLD),
        weekly_tokens=wk_tok,
        weekly_budget=WEEKLY_TOKEN_BUDGET,
        weekly_pct=wk_pct,
        weekly_underutilized=(wk_pct < WEEKLY_UNDERUTIL_THRESHOLD),
        active_windows_last_7d=active_w,
        daily_breakdown=daily,
        last_event_ts=last_ts,
    )


def print_report(r: BurnReport) -> None:
    def bar(pct: float, width: int = 30) -> str:
        filled = int(min(pct, 1.0) * width)
        return "#" * filled + "-" * (width - filled)

    print(f"\n{'='*52}")
    print(f"  claudemaxxing -- token burn report")
    print(f"  {r.now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*52}")

    print(f"\n  5-hour window  ({WINDOW_HOURS}h rolling)")
    print(f"  {bar(r.window_pct)}  {r.window_pct*100:.1f}%")
    print(f"  {r.window_tokens:,} / {r.window_limit:,} effective tokens")
    print(f"  {'!! UNDERUTILIZED' if r.window_underutilized else 'OK on track'}")

    print(f"\n  Weekly (rolling 7 days)")
    print(f"  {bar(r.weekly_pct)}  {r.weekly_pct*100:.1f}%")
    print(f"  {r.weekly_tokens:,} / {r.weekly_budget:,} est. token budget")
    print(f"  {'!! UNDERUTILIZED' if r.weekly_underutilized else 'OK on track'}")
    print(f"  Active windows last 7d: {r.active_windows_last_7d:.0f}")

    print(f"\n  Daily breakdown (last 14 days)")
    today = r.now.date()
    for day, tok in sorted(r.daily_breakdown.items())[-14:]:
        delta = (today - datetime.strptime(day, "%Y-%m-%d").date()).days
        age   = "today" if delta == 0 else f"{delta}d ago"
        print(f"  {day}  {bar(tok / WINDOW_TOKEN_LIMIT, 20)}  {tok:>7,}  ({age})")

    if r.last_event_ts:
        age_mins = (r.now - r.last_event_ts).total_seconds() / 60
        print(f"\n  Last activity: {age_mins:.0f} min ago")

    print(f"{'='*52}\n")


# ── Trigger checks ────────────────────────────────────────────────────────────

def should_burn_tokens(r: BurnReport) -> tuple[bool, str]:
    """Returns (should_burn, reason). True when we should queue up token-burn tasks."""
    reasons = []

    if r.window_underutilized:
        reasons.append(
            f"5-hour window only {r.window_pct*100:.0f}% used "
            f"({r.window_tokens:,}/{r.window_limit:,} tokens)"
        )

    if r.weekly_underutilized:
        reasons.append(
            f"weekly only {r.weekly_pct*100:.0f}% used "
            f"({r.weekly_tokens:,}/{r.weekly_budget:,} est. tokens)"
        )

    # Intentionally uses local time — this is a "local evening" trigger.
    local_now = datetime.now()
    if local_now.weekday() == LAST_NIGHT_WEEKDAY and local_now.hour >= LAST_NIGHT_HOUR:
        reasons.append("Sunday night -- weekly window closing")

    return (True, "; ".join(reasons)) if reasons else (False, "")


if __name__ == "__main__":
    events = load_all_events()
    report = build_report(events)
    print_report(report)
    burn, reason = should_burn_tokens(report)
    if burn:
        print(f"  ACTION: token burn triggered -- {reason}")
        print(f"  Run `python run.py --burn` to execute queued tasks.\n")
