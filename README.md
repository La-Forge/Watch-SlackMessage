

\# Slack → Airtable Collector



Collects Slack messages containing URLs and streams them directly to Airtable — incremental per channel, no local files.



---



\## 1️⃣ Setup



\### Step 1 · Create a Slack Bot



\* Add it to the channels you want to monitor (e.g. `#share\_ia`, `#share\_data`, etc.).

\* Required \*\*Bot Token Scopes\*\*:

&nbsp; `channels:read`, `channels:history`, `users:read`, `reactions:read`

\* Copy your \*\*`SLACK\_BOT\_TOKEN`\*\* (starts with `xoxb-...`).



\### Step 2 · Create an Airtable Token



\* Go to \[Airtable Developer Hub](https://airtable.com/developers/web/api/personal-access-tokens)

\* Create a \*\*Personal Access Token\*\* with:



&nbsp; \* `data.records:read`

&nbsp; \* `data.records:write`

\* Note your \*\*`AIRTABLE\_TOKEN`\*\* and \*\*`AIRTABLE\_BASE\_ID`\*\*.



\### Step 3 · Create an Airtable Table



Create a table named \*\*`Slack\_Messages`\*\* with these columns:



| Field                    | Suggested Type   |

| ------------------------ | ---------------- |

| original\_message         | Long text        |

| url                      | URL              |

| sent\_at                  | Date/time        |

| channel\_name             | Single line text |

| user\_name                | Single line text |

| mentioned\_users          | Long text        |

| original\_thread\_messages | Long text        |

| reaction\_names           | Single line text |

| reaction\_counts          | Single line text |

| reaction\_users           | Long text        |

| extracted\_at             | Date/time        |



---



\## 2️⃣ Environment Variables



Fill `.env` (keep secrets here, \*\*don’t commit it\*\*) based on `.env.example`:



```dotenv

\# Required

SLACK\_BOT\_TOKEN=

AIRTABLE\_TOKEN=

AIRTABLE\_BASE\_ID=

AIRTABLE\_TABLE\_NAME=Slack\_Messages



\# Optional

CHANNEL\_PREFIX=share       # Only channels starting with this prefix

TEST\_MODE=false            # true = single channel + 10-day window

START\_DATE=                # YYYY-MM-DD or ISO8601

END\_DATE=

```



---



\## 3️⃣ Build \& Run



```bash

\# Build

docker build -t slack2airtable:latest .



\# Run (safe: reads from .env)

docker run --rm --env-file .env slack2airtable:latest



\# Optional: override variables

docker run --rm --env-file .env \\

&nbsp; -e TEST\_MODE=true \\

&nbsp; -e START\_DATE=2025-10-01 \\

&nbsp; -e END\_DATE=2025-10-24 \\

&nbsp; slack2airtable:latest

```



---



\## 4️⃣ What the Script Does



\* Reads config from env

\* Lists public channels matching `CHANNEL\_PREFIX`

\* For each channel:



&nbsp; \* Determines time window (`START\_DATE`, `END\_DATE`, or last `sent\_at` in Airtable)

&nbsp; \* Fetches Slack messages containing URLs

&nbsp; \* Extracts metadata (author, mentions, thread replies, reactions)

&nbsp; \* Pushes them to Airtable in batches of 10

\* \*\*Incremental logic\*\*: each run resumes from the last imported `sent\_at`.



---



\## 5️⃣ Tips



\* The bot only sees \*\*public\*\* channels it’s \*\*added to\*\*.

\* To test safely: set `TEST\_MODE=true` (only 1 channel, 10-day window).

\* To re-import older history: set a manual `START\_DATE`.



---



\## 6️⃣ Security



\* `.env` should \*\*never\*\* be committed.



---



\*\*Maintainer:\*\* La Forge

For improvements or issues, reach out internally or open a pull request.



---



