"""Threads where the ball is in Jess's court.

Not an inbox. Unread is the wrong signal, because the mail that actually needs
a reply has usually been read already, and what is left unread is
notifications. The signal that works is: someone else sent the last message,
and Jess is on the To line rather than Cc. Cc means the reply belongs to
whoever was addressed.
"""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Your own address, so the "did they speak last" check knows which side you are.
ME = os.environ.get("HERD_EMAIL", "").lower()

# Senders that are machines. Each one earned its place by showing up in a
# result set and not being a person.
NOISE = [
    "noreply", "no-reply", "notifications", "ringcentral", "googlegroups.com",
    "vimeo.com", "calendar-notification", "mailer-daemon", "postmaster",
]

# Transactional mail addressed to a person but asking for no reply: password
# resets, portal invites, account setup. A real ask never looks like these.
TRANSACTIONAL = (
    "reset your", "finish account setup", "welcome to", "verify your",
    "confirm your email", "your receipt", "invoice", "password",
    "sign in to", "activate your",
)

QUERY = (
    "in:inbox newer_than:8d "
    "-category:promotions -category:social -category:updates "
    + " ".join(f"-from:{n}" for n in NOISE)
)


def _gws(args: list[str], params: dict) -> dict:
    out = subprocess.run(
        ["gws", "gmail", "users", *args, "--params", json.dumps(params), "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return {}


def waiting(limit: int = 40) -> list[dict]:
    listing = _gws(["threads", "list"], {"userId": "me", "q": QUERY, "maxResults": limit})
    threads = listing.get("threads", [])

    # One subprocess per thread, so serially this ran to ~24 seconds. The calls
    # are independent and IO-bound, which is what a thread pool is for.
    def fetch(t):
        return _gws(["threads", "get"], {"userId": "me", "id": t["id"], "format": "metadata"})

    with ThreadPoolExecutor(max_workers=8) as pool:
        fulls = list(pool.map(fetch, threads))

    rows = []
    for thread, full in zip(threads, fulls):
        msgs = full.get("messages", [])
        if not msgs:
            continue

        last = msgs[-1]
        head = {h["name"].lower(): h["value"] for h in last.get("payload", {}).get("headers", [])}

        # Jess spoke last, so it is their turn rather than hers.
        if ME in head.get("from", "").lower():
            continue
        # On Cc only means the reply belongs to whoever is on To.
        if ME not in head.get("to", "").lower():
            continue

        subject = head.get("subject", "(no subject)")
        if any(t in subject.lower() for t in TRANSACTIONAL):
            continue

        when = datetime.fromtimestamp(int(last.get("internalDate", 0)) / 1000)
        sender = head.get("from", "")
        name = sender.split("<")[0].strip().strip('"') or sender

        rows.append({
            "id": thread["id"],
            "from": name,
            "subject": subject,
            "when": when.strftime("%a %H:%M"),
            "sort": when.isoformat(),
            "snippet": (last.get("snippet") or "")[:120],
            "url": f"https://mail.google.com/mail/u/0/#inbox/{thread['id']}",
            "unread": "UNREAD" in last.get("labelIds", []),
        })

    rows.sort(key=lambda r: r["sort"], reverse=True)
    return rows
