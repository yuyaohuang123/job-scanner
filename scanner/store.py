"""Persistent listing store.

The store is a single JSON file committed back to the repo on every run. That
gives us three things for free: a durable record of when each posting was first
seen, a diff against the previous run to drive the email digest, and a full
history in git if we ever want to know when something changed.
"""

import json
import os
from datetime import datetime, timezone

STORE_VERSION = 1


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def listing_key(firm_name, posting):
    """Stable identity for a posting across runs.

    Uses the platform's own requisition id where possible; those survive title
    edits and re-postings, which a title hash would not.
    """
    return f"{firm_name}::{posting['source_id']}".lower()


def load(path):
    if not os.path.exists(path):
        return {"version": STORE_VERSION, "last_scan": None, "listings": {}}
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("listings", {})
    data.setdefault("last_scan", None)
    data.setdefault("version", STORE_VERSION)
    return data


def save(path, store):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def reconcile(store, scanned, scanned_firms):
    """Merge this run's postings into the store.

    Returns (new_items, closed_items). `scanned_firms` is the set of firms that
    actually returned data this run -- a firm whose API errored must not have
    all its listings marked closed just because we couldn't reach it.
    """
    now = _now()
    listings = store["listings"]
    seen_keys = set()
    new_items = []

    for key, posting in scanned.items():
        seen_keys.add(key)
        existing = listings.get(key)

        if existing is None:
            record = dict(posting)
            record["first_seen"] = now
            record["last_seen"] = now
            record["status"] = "open"
            listings[key] = record
            new_items.append(record)
        else:
            # Preserve first_seen; refresh everything else in case the posting
            # was edited (title tweaks and added locations are common).
            first_seen = existing.get("first_seen", now)
            was_closed = existing.get("status") == "closed"
            existing.update(posting)
            existing["first_seen"] = first_seen
            existing["last_seen"] = now
            existing["status"] = "open"
            if was_closed:
                # Reopened postings are worth surfacing again.
                new_items.append(existing)

    closed_items = []
    for key, record in listings.items():
        if key in seen_keys:
            continue
        if record.get("firm") not in scanned_firms:
            continue  # firm wasn't scanned successfully; leave it alone
        if record.get("status") != "closed":
            record["status"] = "closed"
            record["closed_at"] = now
            closed_items.append(record)

    store["last_scan"] = now
    return new_items, closed_items


def open_listings(store):
    return [r for r in store["listings"].values() if r.get("status") == "open"]
