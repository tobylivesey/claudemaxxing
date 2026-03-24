"""
run.py — claudemaxxing orchestrator.

Usage:
  python run.py              # token report + policy check (if due)
  python run.py --burn       # report + print queued tasks if underutilized
  python run.py --policy     # force a policy check now (ignores interval)
  python run.py --status     # short one-liner: tokens + vault progress
  python run.py --vault      # full vault review dashboard
  python run.py --vault-full # vault dashboard + all gaps and issues found
"""

import json
import sys
from pathlib import Path

from analyze import build_report, load_all_events, print_report, should_burn_tokens
from policy_check import print_policy_report, run_policy_check
from usage_api import fetch_usage
from vault_status import one_line_status, print_vault_status

SCRIPT_DIR = Path(__file__).parent
TASKS_PATH = SCRIPT_DIR / "tasks.json"


# ── Task loading ──────────────────────────────────────────────────────────────

def load_tasks() -> tuple[list[dict], float]:
    """
    Returns (enabled_tasks, stop_pct) from tasks.json.
    Reads the file once so print_burn_tasks doesn't need to re-open it.
    """
    if not TASKS_PATH.exists():
        return [], 0.90

    with open(TASKS_PATH) as f:
        data = json.load(f)

    exec_cfg      = data.get("execution", {})
    stop_pct      = exec_cfg.get("stop_at_window_pct", 90) / 100
    skip_disabled = exec_cfg.get("skip_disabled", True)

    tasks = data.get("tasks", [])
    if skip_disabled:
        tasks = [t for t in tasks if t.get("enabled", False)]

    return tasks, stop_pct


# ── Burn task display ─────────────────────────────────────────────────────────

def _truncate(text: str, limit: int = 120) -> str:
    return text[:limit] + "..." if len(text) > limit else text


def print_burn_tasks(report, tasks: list[dict], stop_pct: float) -> None:
    if not tasks:
        print("  No enabled tasks in tasks.json.")
        print("  Copy tasks.example.json -> tasks.json and fill in your real tasks,")
        print("  or use FILL_TASKS_PROMPT.md to generate them with Claude.\n")
        return

    print(f"\n  Token burn tasks (window currently {report.window_pct*100:.0f}% full)")
    print(f"  Will queue tasks until window reaches {stop_pct*100:.0f}%\n")

    tokens_remaining = int((stop_pct - report.window_pct) * report.window_limit)
    if tokens_remaining <= 0:
        print("  Window is already sufficiently full. No tasks needed.\n")
        return

    queued    = 0
    total_est = 0
    for task in tasks:
        est = task.get("estimated_tokens", 10_000)
        if total_est + est > tokens_remaining:
            break
        queued    += 1
        total_est += est
        print(f"  [{queued}] {task['name']}")
        print(f"      dir:    {task.get('working_dir', '(current)')}")
        print(f"      est:    ~{est:,} tokens")
        print(f"      prompt: {_truncate(task['prompt'])}")
        print()

    if queued == 0:
        print("  No tasks small enough to fit in remaining window capacity.\n")
        return

    print(f"  Total queued: {queued} task(s), ~{total_est:,} estimated tokens")
    print(f"\n  To run these, open Claude Code in each project directory")
    print(f"  and paste the prompt shown above, or run:")
    print(f'    cd <working_dir> && claude -p "<prompt>"\n')


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args         = set(sys.argv[1:])
    force_policy = "--policy"    in args
    do_burn      = "--burn"      in args
    status_only  = "--status"    in args
    vault_only   = "--vault"     in args
    vault_full   = "--vault-full" in args

    # Vault-only views — don't load session events
    if vault_only or vault_full:
        print_vault_status(full=vault_full)
        return

    events = load_all_events()
    report = build_report(events)

    if status_only:
        usage = fetch_usage()
        if usage:
            from datetime import timezone
            resets = usage.five_hour_resets_at.astimezone(timezone.utc)
            print(
                f"tokens (live) | window {usage.five_hour_pct:.0f}% | "
                f"7-day {usage.seven_day_pct:.0f}% | "
                f"resets {resets.strftime('%H:%M UTC')}"
            )
        else:
            burn, reason = should_burn_tokens(report)
            flag = "!! UNDERUTILIZED" if burn else "OK on track"
            print(
                f"tokens (local) | window {report.window_pct*100:.0f}% | "
                f"week {report.weekly_pct*100:.0f}% | {flag}"
            )
            if burn:
                print(f"  reason: {reason}")
        print(one_line_status())
        return

    print_report(report)

    burn, reason = should_burn_tokens(report)
    if burn:
        print(f"  !!  Burn triggered: {reason}")
        if do_burn:
            tasks, stop_pct = load_tasks()
            print_burn_tasks(report, tasks, stop_pct)
        else:
            print("  Run `python run.py --burn` to see queued tasks.\n")
    else:
        print("  OK  Usage on track -- no burn needed.\n")

    # Always show a one-line vault summary in the main report
    print(f"  {one_line_status()}\n")

    # Policy check (runs if due, or forced with --policy)
    print_policy_report(run_policy_check(force=force_policy))


if __name__ == "__main__":
    main()
