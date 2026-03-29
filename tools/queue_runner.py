"""Queue runner — stdlib-only CLI for managing SQLite-backed work queues.

Commands:
    init              — Create DB with items + queue_state tables
    add               — Insert items (single URL or batch file)
    claim             — Atomically claim next ready item for a worker
    complete          — Mark item done, record artifact path
    fail              — Mark item failed, increment attempts, record error
    retry             — Reset a failed item back to ready
    status            — Aggregate counts by status
    list              — List items filtered by status
    update-source-memory — Write source memory JSON to a completed item
    refresh-check     — Find items due for refresh and re-queue them
    quick-check       — Efficient recheck using stored source memory selectors
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


# -- Database helpers --------------------------------------------------------

def _db_path(config: dict, config_path: str) -> Path:
    """Return the path to queue.db next to the config file."""
    return Path(config_path).parent / "queue.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with WAL mode for concurrent-reader safety."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection):
    """Run lightweight migrations for schema additions."""
    # Check if items table exists (skip on fresh init before CREATE TABLE)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
    )
    if cur.fetchone() is None:
        return
    # Check if source_memory column exists
    cur = conn.execute("PRAGMA table_info(items)")
    columns = {row[1] for row in cur.fetchall()}
    if "source_memory" not in columns:
        conn.execute("ALTER TABLE items ADD COLUMN source_memory TEXT")
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _next_item_id(conn: sqlite3.Connection) -> str:
    """Generate the next ITEM-NNN id using a counter in queue_state."""
    cur = conn.execute(
        "SELECT value FROM queue_state WHERE key = 'next_item_number'"
    )
    row = cur.fetchone()
    if row is None:
        num = 1
        conn.execute(
            "INSERT INTO queue_state (key, value) VALUES ('next_item_number', '2')"
        )
    else:
        num = int(row["value"])
        conn.execute(
            "UPDATE queue_state SET value = ? WHERE key = 'next_item_number'",
            (str(num + 1),),
        )
    return f"ITEM-{num:03d}"


# -- Commands ----------------------------------------------------------------

def cmd_init(args):
    """Create the SQLite database and tables."""
    config = _load_config(args.config)
    db = _db_path(config, args.config)

    if db.exists() and not args.force:
        print(f"Database already exists: {db}")
        print("Use --force to recreate.")
        sys.exit(1)

    if db.exists() and args.force:
        db.unlink()

    db.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db)
    conn.executescript("""
        CREATE TABLE items (
            item_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'ready',
            custom_data TEXT,
            claimed_by TEXT,
            claimed_at TEXT,
            completed_at TEXT,
            artifact_path TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            error TEXT,
            source_memory TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX idx_items_status ON items(status);

        CREATE TABLE queue_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.execute(
        "INSERT INTO queue_state (key, value) VALUES ('items_processed_today', '0')"
    )
    conn.execute(
        "INSERT INTO queue_state (key, value) VALUES ('learning_iteration', '0')"
    )
    conn.execute(
        "INSERT INTO queue_state (key, value) VALUES ('current_learning_mode', 'intense')"
    )
    conn.commit()
    conn.close()
    print(f"Initialized queue database: {db}")
    print(f"Queue: {config.get('name', config.get('queue_id', 'unnamed'))}")


def cmd_add(args):
    """Add items to the queue."""
    config = _load_config(args.config)
    db = _db_path(config, args.config)
    conn = _connect(db)

    urls = []
    if args.url:
        urls.append(args.url)
    if args.batch_file:
        with open(args.batch_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)

    if not urls:
        print("No URLs provided. Use --url or --batch-file.")
        sys.exit(1)

    now = _now()
    added = 0
    for url in urls:
        item_id = _next_item_id(conn)
        custom_data = json.dumps({"url": url})
        conn.execute(
            """INSERT INTO items (item_id, status, custom_data, created_at, updated_at)
               VALUES (?, 'ready', ?, ?, ?)""",
            (item_id, custom_data, now, now),
        )
        added += 1

    conn.commit()
    conn.close()
    print(f"Added {added} item(s) to queue.")


def cmd_claim(args):
    """Atomically claim the next ready item for a worker."""
    config = _load_config(args.config)
    db = _db_path(config, args.config)
    conn = _connect(db)

    now = _now()
    # Atomic claim: update exactly one ready row
    cur = conn.execute(
        """UPDATE items
           SET status = 'claimed',
               claimed_by = ?,
               claimed_at = ?,
               attempts = attempts + 1,
               updated_at = ?
           WHERE item_id = (
               SELECT item_id FROM items WHERE status = 'ready'
               ORDER BY created_at ASC LIMIT 1
           )
           RETURNING *""",
        (args.worker_id, now, now),
    )
    row = cur.fetchone()
    conn.commit()

    if row is None:
        print("No ready items in queue.")
        conn.close()
        sys.exit(1)

    item = dict(row)
    if item.get("custom_data"):
        item["custom_data"] = json.loads(item["custom_data"])
    conn.close()

    if args.json:
        print(json.dumps(item, indent=2, default=str))
    else:
        print(f"Claimed {item['item_id']} for worker {args.worker_id}")
        if item.get("custom_data"):
            print(f"  URL: {item['custom_data'].get('url', 'N/A')}")


def cmd_complete(args):
    """Mark an item as completed."""
    config = _load_config(args.config)
    db = _db_path(config, args.config)
    conn = _connect(db)

    now = _now()
    cur = conn.execute(
        """UPDATE items
           SET status = 'completed',
               completed_at = ?,
               artifact_path = ?,
               updated_at = ?
           WHERE item_id = ? AND status = 'claimed'""",
        (now, args.artifact_path, now, args.item_id),
    )

    if cur.rowcount == 0:
        print(f"Item {args.item_id} not found or not in 'claimed' status.")
        conn.close()
        sys.exit(1)

    # Increment daily counter
    conn.execute(
        """UPDATE queue_state
           SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)
           WHERE key = 'items_processed_today'"""
    )
    conn.commit()
    conn.close()
    print(f"Completed {args.item_id}")


def cmd_fail(args):
    """Mark an item as failed."""
    config = _load_config(args.config)
    db = _db_path(config, args.config)
    conn = _connect(db)

    now = _now()
    cur = conn.execute(
        """UPDATE items
           SET status = 'failed',
               error = ?,
               updated_at = ?
           WHERE item_id = ? AND status = 'claimed'""",
        (args.error, now, args.item_id),
    )

    if cur.rowcount == 0:
        print(f"Item {args.item_id} not found or not in 'claimed' status.")
        conn.close()
        sys.exit(1)

    conn.commit()
    conn.close()
    print(f"Failed {args.item_id}: {args.error}")


def cmd_retry(args):
    """Reset a failed item back to ready."""
    config = _load_config(args.config)
    db = _db_path(config, args.config)
    conn = _connect(db)

    now = _now()
    cur = conn.execute(
        """UPDATE items
           SET status = 'ready',
               error = NULL,
               claimed_by = NULL,
               claimed_at = NULL,
               updated_at = ?
           WHERE item_id = ? AND status = 'failed'""",
        (now, args.item_id),
    )

    if cur.rowcount == 0:
        print(f"Item {args.item_id} not found or not in 'failed' status.")
        conn.close()
        sys.exit(1)

    conn.commit()
    conn.close()
    print(f"Reset {args.item_id} to ready")


def cmd_status(args):
    """Print aggregate status counts."""
    config = _load_config(args.config)
    db = _db_path(config, args.config)
    conn = _connect(db)

    cur = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM items GROUP BY status ORDER BY status"
    )
    counts = {row["status"]: row["cnt"] for row in cur.fetchall()}
    total = sum(counts.values())

    conn.close()

    if args.json:
        counts["total"] = total
        print(json.dumps(counts))
    else:
        parts = []
        for s in ("ready", "claimed", "completed", "failed"):
            parts.append(f"{s}={counts.get(s, 0)}")
        parts.append(f"total={total}")
        print(", ".join(parts))


def cmd_list(args):
    """List items, optionally filtered by status."""
    config = _load_config(args.config)
    db = _db_path(config, args.config)
    conn = _connect(db)

    query = "SELECT * FROM items"
    params = []

    if args.status:
        query += " WHERE status = ?"
        params.append(args.status)

    query += " ORDER BY created_at ASC"

    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    cur = conn.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    if args.json:
        items = []
        for row in rows:
            item = dict(row)
            if item.get("custom_data"):
                item["custom_data"] = json.loads(item["custom_data"])
            items.append(item)
        print(json.dumps(items, indent=2, default=str))
    else:
        if not rows:
            print("No items found.")
            return
        for row in rows:
            data = json.loads(row["custom_data"]) if row["custom_data"] else {}
            url = data.get("url", "")
            line = f"  {row['item_id']}  [{row['status']:>9s}]  {url}"
            if row["error"]:
                line += f"  error={row['error']}"
            print(line)
        print(f"\n{len(rows)} item(s)")


# -- Source memory & refresh commands ----------------------------------------

def cmd_update_source_memory(args):
    """Write source memory JSON to a completed item."""
    config = _load_config(args.config)
    db = _db_path(config, args.config)
    conn = _connect(db)

    # Accept JSON from --json arg or --file
    if args.json_data:
        sm_json = args.json_data
    elif args.file:
        with open(args.file) as f:
            sm_json = f.read()
    else:
        print("Provide source memory via --json or --file.")
        sys.exit(1)

    # Validate it's valid JSON
    try:
        sm = json.loads(sm_json)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        sys.exit(1)

    # Ensure required fields have sensible defaults
    sm.setdefault("retrieval_method", "agent_recheck")
    sm.setdefault("last_retrieval_path", None)
    sm.setdefault("key_selectors", {})
    sm.setdefault("refresh_script", None)
    sm.setdefault("script_accuracy", None)
    sm.setdefault("method_stable_since", None)

    now = _now()
    cur = conn.execute(
        """UPDATE items
           SET source_memory = ?,
               updated_at = ?
           WHERE item_id = ? AND status = 'completed'""",
        (json.dumps(sm), now, args.item_id),
    )

    if cur.rowcount == 0:
        print(f"Item {args.item_id} not found or not in 'completed' status.")
        conn.close()
        sys.exit(1)

    conn.commit()
    conn.close()
    print(f"Updated source memory for {args.item_id}")


def cmd_refresh_check(args):
    """Find completed items due for refresh and re-queue them.

    An item is due for refresh when:
    - days since completed_at > refresh.interval_days (from config)
    - item status is 'completed'
    """
    config = _load_config(args.config)
    refresh = config.get("refresh", {})

    if not refresh.get("enabled", False):
        print("Refresh is not enabled in queue config.")
        sys.exit(0)

    interval_days = refresh.get("interval_days", 7)
    stale_after_days = refresh.get("stale_after_days", 30)
    mode = refresh.get("mode", "agent_recheck")

    db = _db_path(config, args.config)
    conn = _connect(db)

    now = datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT item_id, custom_data, completed_at, source_memory, artifact_path "
        "FROM items WHERE status = 'completed' AND completed_at IS NOT NULL"
    ).fetchall()

    due = []
    stale = []
    for row in rows:
        try:
            completed = datetime.strptime(
                row["completed_at"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        days_since = (now - completed).total_seconds() / 86400

        if days_since > stale_after_days:
            stale.append(row)
        elif days_since > interval_days:
            due.append(row)

    if not due and not stale:
        print("No items due for refresh.")
        conn.close()
        return

    now_str = _now()
    refreshed = 0

    for row in due:
        custom_data = json.loads(row["custom_data"]) if row["custom_data"] else {}
        custom_data["_refresh"] = True
        custom_data["_refresh_mode"] = mode
        custom_data["_previous_artifact"] = row["artifact_path"]

        # Determine effective mode: if item has source memory with selectors,
        # use the config mode; otherwise fall back to agent_recheck
        sm = json.loads(row["source_memory"]) if row["source_memory"] else None
        effective_mode = mode
        if mode in ("efficient_recheck", "deterministic_script") and not sm:
            effective_mode = "agent_recheck"
        custom_data["_refresh_mode"] = effective_mode

        conn.execute(
            """UPDATE items
               SET status = 'ready',
                   custom_data = ?,
                   claimed_by = NULL,
                   claimed_at = NULL,
                   error = NULL,
                   updated_at = ?
               WHERE item_id = ?""",
            (json.dumps(custom_data), now_str, row["item_id"]),
        )
        refreshed += 1

    # Stale items get marked for refresh regardless of mode
    for row in stale:
        custom_data = json.loads(row["custom_data"]) if row["custom_data"] else {}
        custom_data["_refresh"] = True
        custom_data["_refresh_mode"] = "agent_recheck"  # stale = full agent
        custom_data["_previous_artifact"] = row["artifact_path"]

        conn.execute(
            """UPDATE items
               SET status = 'ready',
                   custom_data = ?,
                   claimed_by = NULL,
                   claimed_at = NULL,
                   error = NULL,
                   updated_at = ?
               WHERE item_id = ?""",
            (json.dumps(custom_data), now_str, row["item_id"]),
        )
        refreshed += 1

    conn.commit()
    conn.close()

    if args.json:
        result = {
            "refreshed": refreshed,
            "due": len(due),
            "stale": len(stale),
            "mode": mode,
        }
        print(json.dumps(result))
    else:
        print(f"Refresh check: {len(due)} due, {len(stale)} stale → {refreshed} re-queued (mode={mode})")


class _SelectorExtractor(HTMLParser):
    """Minimal HTML parser that extracts text from elements matching CSS class/tag selectors."""

    def __init__(self, selectors: dict):
        super().__init__()
        self.selectors = selectors  # {field_name: "css-like selector string"}
        self.results = {}
        self._current_tag = None
        self._current_attrs = {}
        self._capture_for = None  # field name we're capturing
        self._depth = 0
        self._capture_depth = 0
        self._buffer = ""

    def _matches(self, tag, attrs, selector):
        """Check if a tag+attrs matches a simple CSS selector like 'h1.class' or '.class'."""
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()

        # Parse selector: tag.class or .class
        parts = selector.split(".")
        sel_tag = parts[0] if parts[0] else None
        sel_classes = parts[1:] if len(parts) > 1 else []

        if sel_tag and tag != sel_tag:
            return False
        for sc in sel_classes:
            if sc not in classes:
                return False
        return True

    def handle_starttag(self, tag, attrs):
        self._current_tag = tag
        self._current_attrs = dict(attrs)
        self._depth += 1

        if self._capture_for is None:
            for field, selector in self.selectors.items():
                if field not in self.results and self._matches(tag, attrs, selector):
                    self._capture_for = field
                    self._capture_depth = self._depth
                    self._buffer = ""
                    break

        # Also check meta tags (og:title, og:description)
        if tag == "meta":
            attrs_dict = dict(attrs)
            prop = attrs_dict.get("property", "")
            name = attrs_dict.get("name", "")
            content = attrs_dict.get("content", "")
            for field, selector in self.selectors.items():
                if field not in self.results:
                    if selector.startswith("meta["):
                        # Parse meta[property=og:title] style
                        m = re.match(r'meta\[(\w+)=([^\]]+)\]', selector)
                        if m:
                            attr_name, attr_val = m.group(1), m.group(2)
                            if attrs_dict.get(attr_name) == attr_val and content:
                                self.results[field] = content

    def handle_endtag(self, tag):
        if self._capture_for and self._depth == self._capture_depth:
            self.results[self._capture_for] = self._buffer.strip()
            self._capture_for = None
        self._depth -= 1

    def handle_data(self, data):
        if self._capture_for:
            self._buffer += data


def cmd_quick_check(args):
    """Efficient recheck using stored source memory selectors.

    Fetches the item's URL, extracts fields using stored CSS selectors,
    compares to existing artifact data. Reports changed/unchanged.
    """
    config = _load_config(args.config)
    db = _db_path(config, args.config)
    conn = _connect(db)

    row = conn.execute(
        "SELECT * FROM items WHERE item_id = ?", (args.item_id,)
    ).fetchone()

    if row is None:
        print(f"Item {args.item_id} not found.")
        conn.close()
        sys.exit(1)

    if not row["source_memory"]:
        print(f"Item {args.item_id} has no source memory. Use agent_recheck instead.")
        conn.close()
        sys.exit(1)

    sm = json.loads(row["source_memory"])
    selectors = sm.get("key_selectors", {})
    if not selectors:
        print(f"Item {args.item_id} has no key_selectors in source memory.")
        conn.close()
        sys.exit(1)

    custom_data = json.loads(row["custom_data"]) if row["custom_data"] else {}
    url = custom_data.get("url")
    if not url:
        print(f"Item {args.item_id} has no URL in custom_data.")
        conn.close()
        sys.exit(1)

    # Load existing artifact for comparison
    artifact_data = {}
    if row["artifact_path"] and os.path.exists(row["artifact_path"]):
        try:
            with open(row["artifact_path"]) as f:
                artifact = json.load(f)
            artifact_data = artifact.get("extracted", {})
        except (json.JSONDecodeError, OSError):
            pass

    # Fetch the URL
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        result = {"item_id": args.item_id, "status": "fetch_error", "error": str(e)}
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Quick-check {args.item_id}: fetch error — {e}")
        conn.close()
        sys.exit(1)

    # Extract using selectors
    extractor = _SelectorExtractor(selectors)
    extractor.feed(html)
    extracted = extractor.results

    # Compare extracted values to artifact
    changes = {}
    for field, new_val in extracted.items():
        old_val = artifact_data.get(field)
        if old_val is not None and str(old_val) != str(new_val):
            changes[field] = {"old": old_val, "new": new_val}

    changed = len(changes) > 0
    now = _now()

    if not changed:
        # Touch the updated_at timestamp
        conn.execute(
            "UPDATE items SET updated_at = ? WHERE item_id = ?",
            (now, args.item_id),
        )
        conn.commit()

    conn.close()

    result = {
        "item_id": args.item_id,
        "status": "changed" if changed else "unchanged",
        "extracted_fields": len(extracted),
        "changes": changes,
        "checked_at": now,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if changed:
            print(f"Quick-check {args.item_id}: CHANGED — {list(changes.keys())}")
            for field, diff in changes.items():
                print(f"  {field}: {diff['old']!r} → {diff['new']!r}")
        else:
            print(f"Quick-check {args.item_id}: unchanged ({len(extracted)} fields checked)")


# -- CLI entrypoint ----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Queue runner — manage SQLite-backed work queues",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Initialize queue database")
    p_init.add_argument("--config", required=True, help="Path to queue.json")
    p_init.add_argument("--force", action="store_true", help="Recreate if exists")

    # add
    p_add = sub.add_parser("add", help="Add items to queue")
    p_add.add_argument("--config", required=True, help="Path to queue.json")
    p_add.add_argument("--url", help="Single URL to add")
    p_add.add_argument("--batch-file", help="File with one URL per line")

    # claim
    p_claim = sub.add_parser("claim", help="Claim next ready item")
    p_claim.add_argument("--config", required=True, help="Path to queue.json")
    p_claim.add_argument("--worker-id", required=True, help="Worker identifier")
    p_claim.add_argument("--json", action="store_true", help="Output as JSON")

    # complete
    p_complete = sub.add_parser("complete", help="Mark item completed")
    p_complete.add_argument("--config", required=True, help="Path to queue.json")
    p_complete.add_argument("--item-id", required=True, help="Item ID")
    p_complete.add_argument("--artifact-path", required=True, help="Path to artifact JSON")

    # fail
    p_fail = sub.add_parser("fail", help="Mark item failed")
    p_fail.add_argument("--config", required=True, help="Path to queue.json")
    p_fail.add_argument("--item-id", required=True, help="Item ID")
    p_fail.add_argument("--error", required=True, help="Error description")

    # retry
    p_retry = sub.add_parser("retry", help="Reset failed item to ready")
    p_retry.add_argument("--config", required=True, help="Path to queue.json")
    p_retry.add_argument("--item-id", required=True, help="Item ID")

    # status
    p_status = sub.add_parser("status", help="Show queue status counts")
    p_status.add_argument("--config", required=True, help="Path to queue.json")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")

    # list
    p_list = sub.add_parser("list", help="List items")
    p_list.add_argument("--config", required=True, help="Path to queue.json")
    p_list.add_argument("--status", help="Filter by status")
    p_list.add_argument("--limit", type=int, help="Max items to show")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    # update-source-memory
    p_usm = sub.add_parser("update-source-memory", help="Write source memory to item")
    p_usm.add_argument("--config", required=True, help="Path to queue.json")
    p_usm.add_argument("--item-id", required=True, help="Item ID")
    p_usm.add_argument("--json", dest="json_data", help="Source memory JSON string")
    p_usm.add_argument("--file", help="Path to JSON file with source memory")

    # refresh-check
    p_refresh = sub.add_parser("refresh-check", help="Find and re-queue items due for refresh")
    p_refresh.add_argument("--config", required=True, help="Path to queue.json")
    p_refresh.add_argument("--json", action="store_true", help="Output as JSON")

    # quick-check
    p_quick = sub.add_parser("quick-check", help="Efficient recheck using source memory")
    p_quick.add_argument("--config", required=True, help="Path to queue.json")
    p_quick.add_argument("--item-id", required=True, help="Item ID to quick-check")
    p_quick.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "claim": cmd_claim,
        "complete": cmd_complete,
        "fail": cmd_fail,
        "retry": cmd_retry,
        "status": cmd_status,
        "list": cmd_list,
        "update-source-memory": cmd_update_source_memory,
        "refresh-check": cmd_refresh_check,
        "quick-check": cmd_quick_check,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
