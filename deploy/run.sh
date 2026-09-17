#!/bin/sh
# Entry point of the Coolify scheduled task — not of the image.
# The heartbeat is pushed whatever the outcome: the crontab this replaced chained
# it with `&&`, so a failed run pushed nothing and was indistinguishable from a run
# that had not happened yet.
python /app/slack_to_airtable.py
rc=$?

if [ -n "${HEARTBEAT_URL:-}" ]; then
    if [ "$rc" -eq 0 ]; then status=up; else status=down; fi
    python - "$status" "$rc" <<'PY'
import os
import sys
import urllib.parse
import urllib.request

status, rc = sys.argv[1], sys.argv[2]
url = f"{os.environ['HEARTBEAT_URL']}?" + urllib.parse.urlencode(
    {"status": status, "msg": f"slack_to_airtable exit {rc}"}
)
try:
    urllib.request.urlopen(url, timeout=15).read()
except Exception as exc:  # a failed heartbeat must not mask the job's own result
    print(f"heartbeat push failed: {exc}", file=sys.stderr)
PY
fi

exit $rc
