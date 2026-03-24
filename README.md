# claudemaxxing

Token utilisation tracker for Claude Pro subscriptions. Monitors your 5-hour window and weekly burn rate, and automatically runs useful tasks via `claude -p` when tokens would otherwise go to waste.

Designed to run headlessly on an always-on device (homelab, Proxmox VM, home server) so your Pro allocation gets used even while you're asleep.

## How it works

Claude Pro enforces rate limits **per account**, not per machine. Any device authenticated with your Pro account draws from the same 5-hour window. This means you can run burn tasks from a homelab while doing interactive work on a laptop — they share the same pool.

`autoburn.py` checks real utilisation via the claude.ai API before running any task, so it knows the actual server-side state regardless of which machine you're on. If the API isn't configured, it falls back to attempting tasks directly and treating a rate-limit error as the "window full" signal.

```
cron fires every 30 min
  -> autoburn.py
  -> fetches live utilisation from claude.ai API
  -> window >= 80%: skip, log reset time, exit
  -> window < 80%: run tasks
     -> rate limited: window filled up mid-run, stop
     -> success: log output, move to next task
  -> resets next cycle
```

## How token counting works

```
effective_tokens = input_tokens + output_tokens
```

Cache creation tokens are large but discounted by Anthropic and don't count toward window/weekly caps. Only `input + output` is tracked here.

**Pro plan limits (as of 2026-03-21):**
- 5-hour window: ~44,000 effective tokens
- Practical weekly target: 10 windows × 44K = 440K tokens

## Files

| File | Purpose |
|------|---------|
| `analyze.py` | Token analysis — reads local session JSONLs, computes window/weekly burn |
| `run.py` | CLI entry point — interactive report and task queue |
| `autoburn.py` | Headless runner — checks live utilisation, invokes `claude -p` |
| `usage_api.py` | Fetches real-time utilisation from the claude.ai API |
| `burn.sh` | Cron entry point (Linux/macOS) |
| `burn.ps1` | Task Scheduler entry point (Windows, optional) |
| `policy_check.py` | Fetches monitored URLs and diffs rate-limit sections |
| `vault_status.py` | Optional: tracks progress on a knowledge-base review project |
| `config.json` | Plan config, limits, thresholds, autoburn hours, monitored URLs |
| `tasks.example.json` | Example burn task list (copy to `tasks.json` and fill in) |
| `FILL_TASKS_PROMPT.md` | Prompt template for generating your personalised `tasks.json` |
| `VAULT_WORKFLOW.md` | Guide for running vault review sessions |

**Gitignored (personal/runtime):** `tasks.json`, `policy_state.json`, `burn.log`, `cron.log`, `.env`

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/your-username/claudemaxxing.git
cd claudemaxxing
```

Edit `config.json`:
- Set `vault.dir` to your vault repo path if using vault tracking
- Adjust `autoburn.allowed_hours_start/end` if needed (default: 22:00–07:59, overnight)

### 2. Install Claude Code and authenticate

On whichever machine will run the burns:

```bash
npm install -g @anthropic-ai/claude-code
claude   # log in interactively once to authenticate your Pro account
```

### 3. Configure live usage API (recommended)

This gives autoburn real server-side utilisation data, accurate across all your devices.

**Get your org ID:**
Visit `claude.ai/settings/usage`, open DevTools → Network, refresh, find the request to `/api/organizations/.../usage` — the UUID in the URL is your org ID.

**Get your session cookie:**
In DevTools, find that same request → Headers → copy the full `Cookie:` request header value.

Create a `.env` file (gitignored):
```bash
CLAUDE_ORG_ID=your-uuid-here
CLAUDE_SESSION_COOKIE=<paste full Cookie header value>
```

Load it before running (add to your shell profile or cron entry):
```bash
export $(grep -v '^#' .env | xargs)
```

The session cookie will expire eventually. When it does, `autoburn.py` logs a warning and falls back to the rate-limit-as-signal mode automatically — nothing breaks.

### 4. Create your task list

```bash
cp tasks.example.json tasks.json
```

Populate it — see `FILL_TASKS_PROMPT.md` for a ready-made prompt that generates a personalised task list from your projects. `tasks.json` is gitignored so your real paths and prompts stay local.

### 5. Run manually

```bash
python run.py              # full token report
python run.py --status     # one-liner: live tokens + vault progress
python run.py --burn       # show queued burn tasks
python run.py --policy     # force policy check now
python run.py --vault      # vault review dashboard (if configured)
```

### 6. Set up auto-burn (cron)

```bash
chmod +x burn.sh
crontab -e

# Run every 30 minutes — autoburn.py handles the allowed_hours gate
*/30 * * * * /path/to/claudemaxxing/burn.sh >> /path/to/claudemaxxing/cron.log 2>&1
```

`autoburn.py` will only fire tasks during the hours set in `config.json` (`allowed_hours_start`/`allowed_hours_end`). Default is 22:00–07:59 (overnight), which is ideal for a homelab running while you sleep. Set both to `0` to allow all hours.

**Requirements:**
- Machine must be on (cron can't wake a sleeping machine — use an always-on homelab)
- `claude` CLI in PATH and authenticated to your Pro account
- `tasks.json` present with at least one enabled task

### 7. Windows (Task Scheduler, optional)

```powershell
schtasks /create /tn "claudemaxxing-autoburn" /tr "powershell -File C:\path\to\burn.ps1" /sc hourly /mo 2
```

## Usage notes

- `claude -p` uses your Pro subscription directly — no API key needed
- Tokens are account-wide: running burns from a homelab counts against the same window as your laptop usage
- The policy checker fingerprints Anthropic's rate-limit docs every 14 days and alerts you if anything changes
- The Sunday night trigger in `analyze.py` fires at 21:00 local time regardless of window fill, as a last-chance burn before the weekly window resets
