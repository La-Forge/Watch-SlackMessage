# Slack → Airtable Collector

Collects Slack messages containing URLs and streams them directly to Airtable — incremental per channel, no local files.

---

## 1️⃣ Setup

### Step 1 · Create a Slack Bot

* Add it to the channels you want to monitor (e.g. `#share_ia`, `#share_data`, etc.).
* Required **Bot Token Scopes**:
  `channels:read`, `channels:history`, `users:read`, `reactions:read`
* Copy your **`SLACK_BOT_TOKEN`** (starts with `xoxb-...`).

### Step 2 · Create an Airtable Token

* Go to [Airtable Developer Hub](https://airtable.com/developers/web/api/personal-access-tokens)
* Create a **Personal Access Token** with:

  * `data.records:read`
  * `data.records:write`
* Note your **`AIRTABLE_TOKEN`** and **`AIRTABLE_BASE_ID`**.

### Step 3 · Create an Airtable Table

Create a table named **`Slack_Messages`** with these columns:

| Field                    | Suggested Type   |
| ------------------------ | ---------------- |
| original_message         | Long text        |
| url                      | URL              |
| sent_at                  | Date/time        |
| channel_name             | Single line text |
| user_name                | Single line text |
| mentioned_users          | Long text        |
| original_thread_messages | Long text        |
| reaction_names           | Single line text |
| reaction_counts          | Single line text |
| reaction_users           | Long text        |
| extracted_at             | Date/time        |

---

## 2️⃣ Environment Variables

Fill `.env` (keep secrets here, **don’t commit it**) based on `.env.example`:

```dotenv
# Required
SLACK_BOT_TOKEN=
AIRTABLE_TOKEN=
AIRTABLE_BASE_ID=
AIRTABLE_TABLE_NAME=Slack_Messages

# Optional
CHANNEL_PREFIX=share       # Only channels starting with this prefix
TEST_MODE=false            # true = single channel + 10-day window
START_DATE=                # YYYY-MM-DD or ISO8601
END_DATE=
```

---

## 3️⃣ Build & Run

```bash
# Build
docker build -t slack2airtable:latest .

# Run (safe: reads from .env)
docker run --rm --env-file .env slack2airtable:latest

# Optional: override variables
docker run --rm --env-file .env \
  -e TEST_MODE=true \
  -e START_DATE=2025-10-01 \
  -e END_DATE=2025-10-24 \
  slack2airtable:latest
```

---

## 4️⃣ What the Script Does

* Reads config from env
* Lists public channels matching `CHANNEL_PREFIX`
* For each channel:

  * Determines time window (`START_DATE`, `END_DATE`, or last `sent_at` in Airtable)
  * Fetches Slack messages containing URLs
  * Extracts metadata (author, mentions, thread replies, reactions)
  * Pushes them to Airtable in batches of 10
* **Incremental logic**: each run resumes from the last imported `sent_at`.

---

## 5️⃣ Tips

* The bot only sees **public** channels it’s **added to**.
* To test safely: set `TEST_MODE=true` (only 1 channel, 10-day window).
* To re-import older history: set a manual `START_DATE`.

---

## 6️⃣ Security

* `.env` should **never** be committed.
* In production the variables live in Coolify, not in a file on the host.

---

## 7️⃣ Production deployment (Coolify)

The collector runs on **redwin** as a Coolify *Docker Compose* application built
from `docker-compose.yaml` at the root of this repository.

The container does nothing on its own: its entrypoint is overridden to
`sleep infinity`, and a Coolify **scheduled task** execs the real run into it
every Sunday at 20:00 UTC:

```text
Frequency : 0 20 * * 0
Command   : sh /app/run.sh
Container : watch-slackmessage
```

`run.sh` runs the collector, then pushes the uptime-kuma heartbeat named by
`HEARTBEAT_URL` with `status=up` or `status=down`, and exits with the collector's
own status so a failure shows up in the task's execution log.

Variables are set on the Coolify resource (`SLACK_BOT_TOKEN`, `AIRTABLE_TOKEN`,
`AIRTABLE_BASE_ID`, `AIRTABLE_TABLE_NAME`, optionally `CHANNEL_PREFIX`,
`TEST_MODE`, `HEARTBEAT_URL`). To run the collection out of schedule:

```bash
docker exec "$(docker ps -q --filter label=coolify.resourceName=watch-slackmessage)" sh /app/run.sh
```

---

**Maintainer:** La Forge
For improvements or issues, reach out internally or open a pull request.
