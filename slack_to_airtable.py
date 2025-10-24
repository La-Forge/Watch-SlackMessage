# -*- coding: utf-8 -*-
"""
End-to-end: Slack -> (clean) -> Airtable
- Fetch messages (with URLs) from Slack channels.
- Incremental per channel: if START_DATE is not provided, the script reads Airtable
  to find the latest `sent_at` for that channel and uses it as the `oldest` timestamp.
- Optional END_DATE (exclusive). If not set, use "now".
- No local TSV; records are streamed to Airtable in batches.

Env vars:
  SLACK_BOT_TOKEN        (required)
  AIRTABLE_TOKEN         (required)
  AIRTABLE_BASE_ID       (required)
  AIRTABLE_TABLE_NAME    (required)
  CHANNEL_PREFIX         (default: "share")   # only channels whose names start with this prefix
  TEST_MODE              (default: "false")   # "true" limits to 1 channel and uses the 10-day window rule
  START_DATE             (optional, ISO 8601 or "YYYY-MM-DD")
  END_DATE               (optional, ISO 8601 or "YYYY-MM-DD")
"""

import os, re, time, json, html, typing as t
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
from dateutil import parser as dateparser
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ---------------------- Config from env ----------------------
SLACK_BOT_TOKEN   = os.environ.get("SLACK_BOT_TOKEN")
AIRTABLE_TOKEN    = os.environ.get("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID  = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE    = os.environ.get("AIRTABLE_TABLE_NAME")
CHANNEL_PREFIX    = os.environ.get("CHANNEL_PREFIX", "share")
TEST_MODE         = os.environ.get("TEST_MODE", "false").lower() == "true"

START_DATE_ENV    = os.environ.get("START_DATE")  # optional
END_DATE_ENV      = os.environ.get("END_DATE")    # optional

assert SLACK_BOT_TOKEN,  "SLACK_BOT_TOKEN is required"
assert AIRTABLE_TOKEN,   "AIRTABLE_TOKEN is required"
assert AIRTABLE_BASE_ID, "AIRTABLE_BASE_ID is required"
assert AIRTABLE_TABLE,   "AIRTABLE_TABLE_NAME is required"

AIRTABLE_API = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}"
HEADERS_AT = {"Authorization": f"Bearer {AIRTABLE_TOKEN}", "Content-Type": "application/json"}

client = WebClient(token=SLACK_BOT_TOKEN)
user_cache: dict[str, str] = {}

BATCH_SIZE_AT = 10  # Airtable max 10 per request


# ---------------------- Utilities ----------------------
def to_epoch_seconds(dt: datetime) -> float:
    """Convert aware datetime to Slack 'ts' (epoch seconds)."""
    return dt.timestamp()

def parse_date_env(s: str | None) -> datetime | None:
    """Parse ISO/'YYYY-MM-DD' into an aware UTC datetime (start of day for date-only)."""
    if not s:
        return None
    dt = dateparser.parse(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt

# Parse optional global dates (used in NORMAL mode and as fallbacks)
START_DT = parse_date_env(START_DATE_ENV)
END_DT   = parse_date_env(END_DATE_ENV)
if END_DT and END_DT.hour == 0 and END_DT.minute == 0 and END_DT.second == 0:
    # If END_DATE is date-only, use end-of-day (exclusive in Slack API call)
    END_DT = END_DT.replace(hour=23, minute=59, second=59, microsecond=999999)

def clean_html_entities(s: str) -> str:
    return html.unescape(s or "")

def strip_slack_brackets(s: str) -> str:
    # <url|label> or <url> -> url
    return re.sub(r"<([^>|]+)\|?[^>]*>", r"\1", s or "")

def clean_text(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = clean_html_entities(s)
    s = strip_slack_brackets(s)
    return s

def extract_urls(text: str) -> list[str]:
    return [u.strip("<>") for u in re.findall(r"(https?://\S+)", text or "")]

def get_user_name(user_id: str) -> str:
    if not user_id:
        return "unknown"
    if user_id in user_cache:
        return user_cache[user_id]
    try:
        info = client.users_info(user=user_id)
        name = info["user"].get("real_name") or info["user"].get("name") or user_id
        user_cache[user_id] = name
        return name
    except Exception:
        return user_id

def extract_reactions(reactions: list[dict]) -> tuple[str, str, str]:
    """Return (names_csv, counts_csv, users_csv)."""
    if not reactions:
        return "", "", ""
    names, counts, users = [], [], []
    for r in reactions:
        names.append(r.get("name", ""))
        counts.append(str(r.get("count", 0)))
        user_names = [get_user_name(uid) for uid in r.get("users", [])]
        users.append(" / ".join(user_names))
    return ", ".join(names), ", ".join(counts), " | ".join(users)

# ---------------------- Airtable helpers ----------------------
def airtable_request(method: str, url: str, **kwargs):
    """Airtable request with 429 retry."""
    max_retries, backoff = 5, 1.3
    for i in range(max_retries):
        r = requests.request(method, url, headers=HEADERS_AT, timeout=30, **kwargs)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", 1)) * (backoff ** i)
            time.sleep(wait); continue
        if r.ok:
            return r
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise RuntimeError(f"Airtable {r.status_code}: {detail}")
    raise RuntimeError("Airtable: exceeded max retries")

def airtable_latest_for_channel(channel_name: str, field_name: str = "sent_at") -> datetime | None:
    """
    Query Airtable for the latest sent_at for a specific channel.
    Returns aware UTC datetime or None if no record found.
    """
    # filterByFormula with exact match on channel_name, then sort by sent_at desc
    params = {
        "maxRecords": 1,
        "filterByFormula": f"{{channel_name}} = '{channel_name}'",
        "sort[0][field]": field_name,
        "sort[0][direction]": "desc",
    }
    data = airtable_request("GET", AIRTABLE_API, params=params).json()
    recs = data.get("records", [])
    if not recs:
        return None
    val = recs[0].get("fields", {}).get(field_name)
    if not val:
        return None
    ts = pd.to_datetime(val, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()

def airtable_batch_create(rows: list[dict], typecast: bool = True) -> int:
    """Create records in batches of 10."""
    created = 0
    for i in range(0, len(rows), BATCH_SIZE_AT):
        batch = rows[i:i+BATCH_SIZE_AT]
        payload = {"records": [{"fields": r} for r in batch], "typecast": typecast}
        airtable_request("POST", AIRTABLE_API, data=json.dumps(payload))
        created += len(batch)
        time.sleep(0.25)  # polite throttling
    return created

# ---------------------- Slack fetchers ----------------------
def get_thread_replies(channel_id: str, thread_ts: str, limit: int = 15) -> list[str]:
    """Return thread replies' texts (excluding the root)."""
    try:
        res = client.conversations_replies(channel=channel_id, ts=thread_ts, limit=limit)
        return [clean_text(m.get("text", "")) for m in res.get("messages", [])[1:]]
    except Exception:
        return []

def get_messages_in_window(channel_id: str, oldest: float | None, latest: float | None, page_limit: int = 50) -> list[dict]:
    """
    Fetch messages from Slack channel within [oldest, latest] (Slack 'oldest' inclusive, 'latest' exclusive).
    Handles pagination + rate limiting.
    """
    messages, cursor = [], None
    for page in range(page_limit):
        try:
            kwargs = {"channel": channel_id, "limit": 200}
            if cursor: kwargs["cursor"] = cursor
            if oldest is not None: kwargs["oldest"] = str(oldest)
            if latest is not None: kwargs["latest"] = str(latest)

            res = client.conversations_history(**kwargs)
            page_msgs = res.get("messages", [])
            messages.extend(page_msgs)

            cursor = res.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

            time.sleep(1.2)  # gentle limit

        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                retry_after = int(e.response.headers.get("Retry-After", 60))
                time.sleep(retry_after)
                continue
            else:
                print(f"Slack API error: {e.response.get('error')}")
                break
        except Exception as ex:
            print(f"Unexpected Slack error: {ex}")
            break
    return messages

# ---------------------- Main pipeline ----------------------
def process_and_push(channels: list[dict]) -> int:
    """
    For each channel:
      - decide oldest/latest window,
      - fetch messages from Slack,
      - extract URL rows,
      - push to Airtable (batch).
    Returns total inserted rows.
    """
    total_inserted = 0

    for ch in channels:
        ch_id, ch_name = ch["id"], ch["name"]
        print(f"\n== Channel: {ch_name}")

        # --- Decide window (per-channel) ---
        latest_from_airtable = airtable_latest_for_channel(ch_name, field_name="sent_at")

        if TEST_MODE:
            # TEST MODE: window = [Airtable.latest_sent_at, Airtable.latest_sent_at + 10 days)
            if latest_from_airtable:
                oldest_dt = latest_from_airtable
            else:
                # If Airtable has no records for this channel:
                # 1) if user provided START_DATE, use it
                # 2) otherwise, use now - 10 days (small safe window)
                oldest_dt = START_DT or (datetime.now(timezone.utc) - timedelta(days=10))

            candidate_end = oldest_dt + timedelta(days=10)
            latest_dt = min(candidate_end, datetime.now(timezone.utc))
        else:
            # NORMAL MODE:
            # Oldest priority: explicit START_DATE → Airtable.latest_sent_at → None (full history)
            if START_DT:
                oldest_dt = START_DT
            elif latest_from_airtable:
                oldest_dt = latest_from_airtable
            else:
                oldest_dt = None  # no lower bound

            # Latest priority: explicit END_DATE → now
            latest_dt = END_DT or datetime.now(timezone.utc)

        oldest_ts = to_epoch_seconds(oldest_dt) if oldest_dt else None
        latest_ts = to_epoch_seconds(latest_dt) if latest_dt else None

        print(f"Window for #{ch_name}: oldest={oldest_dt}  latest={latest_dt}")

        # --- Fetch ---
        raw_messages = get_messages_in_window(ch_id, oldest_ts, latest_ts)

        # --- Transform ---
        rows: list[dict] = []
        for msg in raw_messages:
            text = clean_text(msg.get("text", ""))
            urls = extract_urls(text)
            if not urls:
                continue

            user_id = msg.get("user", "bot_or_unknown")
            user_name = get_user_name(user_id)

            mentions_ids = re.findall(r"<@([A-Z0-9]+)>", msg.get("text", "") or "")
            mentions_names = sorted({get_user_name(uid) for uid in mentions_ids})

            ts = msg.get("ts", "")  # Slack ts like "1234567890.000000"
            thread_ts = msg.get("thread_ts") or ts
            thread_msgs = get_thread_replies(ch_id, thread_ts)

            names_csv, counts_csv, users_csv = extract_reactions(msg.get("reactions", []))

            # Slack ts -> datetime UTC
            try:
                sent_dt = datetime.fromtimestamp(float(ts.split(".")[0]), tz=timezone.utc)
            except Exception:
                sent_dt = None

            for url in urls:
                rows.append({
                    "channel_name": ch_name,
                    "user_name": user_name,
                    "mentioned_users": ", ".join(mentions_names),
                    "url": url,
                    "original_message": text,
                    "original_thread_messages": thread_msgs,  # Airtable "Long text" field recommended
                    "reaction_names": names_csv,
                    "reaction_counts": counts_csv,
                    "reaction_users": users_csv,
                    "sent_at": sent_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if sent_dt else "",
                    "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

        if not rows:
            print("No new rows.")
            continue

        # --- Load to Airtable ---
        inserted = airtable_batch_create(rows, typecast=True)
        total_inserted += inserted
        print(f"Inserted {inserted} rows for channel '{ch_name}'")

    return total_inserted


def main():
    # Discover channels by prefix
    chans = client.conversations_list(types="public_channel")["channels"]
    share_channels = [c for c in chans if c.get("name", "").startswith(CHANNEL_PREFIX)]
    print(f"Found {len(share_channels)} channels with prefix='{CHANNEL_PREFIX}'")

    if TEST_MODE and share_channels:
        share_channels = share_channels[:1]
        print(f"TEST_MODE=ON, only 1 channel: {share_channels[0]['name']}")

    total = process_and_push(share_channels)
    print(f"\nAll done. Total inserted: {total}")


if __name__ == "__main__":
    main()
