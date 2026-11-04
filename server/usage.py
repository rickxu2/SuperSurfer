"""Allowlisted provider observations, never billing estimates derived from tokens.

Consumption covers observed SuperSurfer sessions on this host (across logins),
not an account's complete bill. Cumulative samples replace themselves on replay.
"""
import math
import time
from datetime import datetime


def number(value):
    return value if type(value) in (int, float) and 0 <= value <= 1e18 and math.isfinite(value) else None


def initialize(db):
    db.execute("CREATE TABLE IF NOT EXISTS provider_usage (metric TEXT, sample TEXT, value REAL, source TEXT, observed REAL, PRIMARY KEY(metric,sample))")
    db.commit()


def record(bridge, metric, sample, value, source):
    value = number(value)
    if value is None or not sample:
        return
    with bridge._lock:
        # Providers can repeat cumulative results or emit zero on a crash.
        bridge._db.execute("INSERT INTO provider_usage VALUES(?,?,?,?,?) ON CONFLICT(metric,sample) DO UPDATE SET value=max(value,excluded.value), observed=excluded.observed",
                           (metric, str(sample), value, source, time.time()))
        bridge._db.commit()


def consumption(bridge):
    with bridge._lock:
        rows = list(bridge._db.execute("SELECT metric,sum(value),max(observed),group_concat(DISTINCT source),count(*) FROM provider_usage GROUP BY metric"))
    metrics = {key: {"value": value, "observed_at": observed, "source": source, "samples": count} for key, value, observed, source, count in rows}
    return {"tokens": metrics.get("tokens"), "cost_usd": metrics.get("cost_usd"),
            "scope": "Observed SuperSurfer sessions on this host, across accounts; excludes native-owner agents and unreported usage. Resumed session totals may include earlier activity.",
            "cost_note": "Provider-reported cost estimate, not an invoice. Missing values are unavailable, not zero."}


def claude_result(bridge, chat, value):
    session = chat.get("thread_id")
    if not session:
        return
    # Stream-json result usage is per turn; total_cost_usd is session cumulative.
    data = value.get("usage") or {}
    if isinstance(data, dict):
        keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
        counts = [number(data.get(key)) for key in keys]
        if chat.get("turn_id") and counts[0] is not None and counts[1] is not None:
            record(bridge, "tokens", session + ":" + str(chat["turn_id"]), sum(x or 0 for x in counts), "Claude result.usage (main agent turns)")
    record(bridge, "cost_usd", session, value.get("total_cost_usd"), "Claude result.total_cost_usd (session estimate)")


def acp_update(bridge, chat, update):
    # ACP used/size are context occupancy, NOT tokens consumed or account quota.
    cost = update.get("cost") or {}
    if isinstance(cost, dict) and cost.get("currency") == "USD":
        record(bridge, "cost_usd", chat.get("thread_id"), cost.get("amount"), "ACP usage_update.cost (session estimate)")


def account_tokens(result):
    """Account lifetime tokens are separate from this host's observed sessions."""
    summary = result.get("summary") if isinstance(result, dict) else None
    total = number(summary.get("lifetimeTokens")) if isinstance(summary, dict) else None
    return {"value": total, "source": "Codex account/usage/read", "observed_at": time.time(),
            "scope": "Account lifetime tokens across clients; separate from host observations."} if total is not None else None


def claude_quota(result):
    windows = []
    limits = result.get("rate_limits") if isinstance(result, dict) else None
    if isinstance(limits, dict) and result.get("rate_limits_available") is True:
        for key, minutes in (("five_hour", 300), ("seven_day", 10080), ("seven_day_oauth_apps", 10080),
                             ("seven_day_opus", 10080), ("seven_day_sonnet", 10080)):
            window = limits.get(key)
            if not isinstance(window, dict):
                continue
            used = number(window.get("utilization"))
            if used is None:
                continue
            reset = None
            try:
                parsed = datetime.fromisoformat(window["resets_at"].replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    reset = number(parsed.timestamp())
            except (KeyError, AttributeError, ValueError, TypeError, OverflowError):
                pass
            windows.append({"label": key.replace("_", " "), "remaining_percent": max(0, 100-used),
                            "window_minutes": minutes, "resets_at": reset})
    return {"status": "available" if windows else "unavailable", "windows": windows,
            "observed_at": time.time() if windows else None, "source": "Claude get_usage (experimental CLI control)",
            "note": "Experimental provider interface; older CLIs, API-key accounts or missing profile access may not expose plan quota."}


def antigravity_quota(result):
    """Only native read-only /usage command data, never response text or tokens."""
    windows = []
    command = result.get("command") if isinstance(result, dict) else None
    valid = (isinstance(command, dict) and command.get("name") in {"usage", "/usage"}
             and result.get("status") == "SUCCESS" and type(result.get("num_turns")) is int
             and result["num_turns"] == 0 and not result.get("conversation_id"))
    data = command.get("data") if valid else None
    groups = data.get("groups") if isinstance(data, dict) else None
    if isinstance(groups, list):
        for group in groups[:30]:
            name = group.get("name") if isinstance(group, dict) else None
            buckets = group.get("buckets") if isinstance(group, dict) else None
            if not isinstance(name, str) or not 0 < len(name) <= 100 or any(ord(c) < 32 for c in name) or not isinstance(buckets, list):
                continue
            for bucket in buckets[:10]:
                if not isinstance(bucket, dict):
                    continue
                fraction = number(bucket.get("remaining_fraction"))
                if fraction is None or fraction > 1:
                    continue
                reset = None
                try:
                    parsed = datetime.fromisoformat(bucket["reset_time"].replace("Z", "+00:00"))
                    if parsed.tzinfo is not None:
                        reset = number(parsed.timestamp())
                except (KeyError, AttributeError, ValueError, TypeError, OverflowError):
                    pass
                period = bucket.get("window")
                period = period if period in {"weekly", "daily", "monthly", "five_hour"} else "quota"
                windows.append({"label": name + " · " + period.replace("_", " "), "group": name,
                                "remaining_percent": round(100 * fraction, 6), "resets_at": reset,
                                "window_minutes": {"weekly": 10080, "daily": 1440, "five_hour": 300}.get(period)})
                if len(windows) >= 30:
                    break
            if len(windows) >= 30:
                break
    return {"status": "available" if windows else "unavailable", "windows": windows,
            "observed_at": time.time() if windows else None, "source": "Antigravity CLI read-only /usage",
            "label": "CLI account quota", "grouped": True,
            "note": "For the Google account signed into agy on this host; it can differ from the ACP account. Extra AI credit balance is separate."}


def quota(result):
    """Normalize account quota snapshots; drop unknown fields and all credentials."""
    windows = []
    snapshots = result.get("rateLimitsByLimitId")
    if not isinstance(snapshots, dict) or not snapshots:
        snapshots = {"codex": result.get("rateLimits")}
    for limit_id, snapshot in list(snapshots.items())[:30]:
        if not isinstance(snapshot, dict):
            continue
        for name in ("primary", "secondary"):
            window = snapshot.get(name)
            if not isinstance(window, dict):
                continue
            used = number(window.get("usedPercent"))
            if used is None:
                continue
            windows.append({"label": str(limit_id)[:100] + " · " + name, "remaining_percent": max(0, 100 - used),
                            "window_minutes": number(window.get("windowDurationMins")), "resets_at": number(window.get("resetsAt"))})
        monthly = snapshot.get("individualLimit")
        if isinstance(monthly, dict) and number(monthly.get("remainingPercent")) is not None:
            windows.append({"label": str(limit_id)[:100] + " · monthly", "remaining_percent": min(100, monthly["remainingPercent"]),
                            "window_minutes": None, "resets_at": number(monthly.get("resetsAt"))})
        credits = snapshot.get("credits")
        if isinstance(credits, dict):
            try:
                balance = number(float(credits.get("balance"))) if isinstance(credits.get("balance"), str) else number(credits.get("balance"))
            except ValueError:
                balance = None
            if credits.get("unlimited") is True or balance is not None:
                windows.append({"label": str(limit_id)[:100] + " · credits", "remaining_credits": balance,
                                "unlimited": credits.get("unlimited") is True})
    return {"windows": windows, "observed_at": time.time() if windows else None,
            "source": "Codex account/rateLimits/read", "status": "available" if windows else "unavailable",
            "note": None if windows else "This account or CLI did not report account quota windows."}
