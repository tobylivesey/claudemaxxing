"""
usage_api.py — fetches real-time token utilisation from the claude.ai API.

Requires two environment variables:
  CLAUDE_ORG_ID          — your organisation UUID (from the URL when you visit
                           claude.ai/settings/usage in your browser)
  CLAUDE_SESSION_COOKIE  — the full Cookie: header value from a logged-in
                           browser request to that same endpoint

How to get these:
  1. Open claude.ai/settings/usage in your browser
  2. Open DevTools -> Network tab -> refresh the page
  3. Find the request to /api/organizations/.../usage
  4. Copy the org UUID from the request URL -> CLAUDE_ORG_ID
  5. Copy the full "Cookie" request header value -> CLAUDE_SESSION_COOKIE

Session expiry:
  Claude uses an opaque session token (sessionKey), not a JWT, so expiry
  cannot be decoded from the value. To check when it expires:
  DevTools -> Application -> Cookies -> claude.ai -> sessionKey -> Expires column.

  When the session expires, fetch_usage() raises SessionExpiredError and
  autoburn falls back to rate-limit-as-signal mode automatically.
"""

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime


USAGE_URL = "https://claude.ai/api/organizations/{org_id}/usage"


@dataclass
class UsageData:
    five_hour_pct: float          # 0–100
    five_hour_resets_at: datetime
    seven_day_pct: float          # 0–100
    seven_day_resets_at: datetime


def fetch_usage() -> UsageData | None:
    """
    Fetch live utilisation from the claude.ai API.
    Returns None if env vars are missing or the request fails.
    Raises SessionExpiredError on 401.
    """
    org_id = os.environ.get("CLAUDE_ORG_ID", "").strip()
    cookie = os.environ.get("CLAUDE_SESSION_COOKIE", "").strip()

    if not org_id or not cookie:
        return None

    url = USAGE_URL.format(org_id=org_id)
    req = urllib.request.Request(
        url,
        headers={
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SessionExpiredError("CLAUDE_SESSION_COOKIE has expired — refresh it")
        return None
    except Exception:
        return None

    try:
        return UsageData(
            five_hour_pct=float(data["five_hour"]["utilization"]),
            five_hour_resets_at=datetime.fromisoformat(data["five_hour"]["resets_at"]),
            seven_day_pct=float(data["seven_day"]["utilization"]),
            seven_day_resets_at=datetime.fromisoformat(data["seven_day"]["resets_at"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


class SessionExpiredError(Exception):
    pass
