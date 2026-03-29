"""Discovery runner — find new queue items from tori.fi search results.

Uses JSON-LD structured data embedded in tori.fi search pages to discover
item URLs. Deduplicates against the existing queue and adds new items.

Commands:
    run      — Execute discovery (default)
    preview  — Show what would be discovered without adding

Usage:
    python3 tools/discovery_runner.py --config .operations/tori-scanner/queue.json
    python3 tools/discovery_runner.py --config .operations/tori-scanner/queue.json --dry-run
    python3 tools/discovery_runner.py --config .operations/tori-scanner/queue.json --query "sähköpyörä"
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DISCOVERY_VERSION = "1.0.0"

# HTTP request settings
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 1.5  # seconds between requests to avoid rate limiting

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [discovery] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("discovery")


# -- Config & DB helpers -----------------------------------------------------


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return json.load(f)


def get_discovery_config(config: dict) -> dict:
    """Extract discovery section with defaults."""
    dc = config.get("discovery", {})
    return {
        "enabled": dc.get("enabled", False),
        "sample_item_url": dc.get("sample_item_url", ""),
        "query_hints": dc.get("query_hints", ""),
        "batch_size": dc.get("batch_size", 20),
        "trigger_threshold": dc.get("trigger_threshold", 10),
        "max_discovery_attempts": dc.get("max_discovery_attempts", 3),
        "search_base_url": dc.get(
            "search_base_url",
            "https://www.tori.fi/recommerce/forsale/search",
        ),
    }


def get_existing_urls(config_path: str) -> set:
    """Get all URLs already in the queue (any status)."""
    db_path = Path(config_path).parent / "queue.db"
    if not db_path.exists():
        return set()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT custom_data FROM items").fetchall()
    conn.close()

    urls = set()
    for row in rows:
        try:
            data = json.loads(row["custom_data"])
            url = data.get("url", "")
            if url:
                urls.add(url)
                # Also normalize: extract item ID for comparison
                m = re.search(r"/item/(\d+)", url)
                if m:
                    urls.add(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass
    return urls


def get_queue_counts(config_path: str) -> dict:
    """Get queue status counts."""
    runner = str(Path(__file__).resolve().parent / "queue_runner.py")
    import subprocess

    result = subprocess.run(
        [sys.executable, runner, "status", "--config", config_path, "--json"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {}


def add_item_to_queue(config_path: str, url: str) -> bool:
    """Add a single item URL to the queue. Returns True on success."""
    import subprocess

    runner = str(Path(__file__).resolve().parent / "queue_runner.py")
    result = subprocess.run(
        [sys.executable, runner, "add", "--config", config_path, "--url", url],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


# -- Tori.fi search & extraction --------------------------------------------


def fetch_search_page(search_url: str) -> str:
    """Fetch a tori.fi search page and return HTML."""
    req = urllib.request.Request(
        search_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "fi-FI,fi;q=0.9,en-US;q=0.8",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
    return resp.read().decode("utf-8", errors="replace")


def extract_items_from_jsonld(html: str) -> list:
    """Extract item data from JSON-LD CollectionPage in HTML.

    Returns list of dicts with: url, name, description, price, condition, image
    """
    items = []

    # Find all JSON-LD script blocks
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)

    for script_content in scripts:
        if "CollectionPage" not in script_content:
            continue

        try:
            data = json.loads(script_content)
        except json.JSONDecodeError:
            continue

        if data.get("@type") != "CollectionPage":
            continue

        main_entity = data.get("mainEntity", {})
        list_elements = main_entity.get("itemListElement", [])

        for element in list_elements:
            product = element.get("item", {})
            if not product.get("url"):
                continue

            offers = product.get("offers", {})
            item = {
                "url": product["url"],
                "name": product.get("name", ""),
                "description": product.get("description", ""),
                "price": offers.get("price"),
                "currency": offers.get("priceCurrency", "EUR"),
                "condition": product.get("itemCondition", ""),
                "image": product.get("image", ""),
                "brand": "",
            }

            # Extract brand if present
            brand = product.get("brand", {})
            if isinstance(brand, dict):
                item["brand"] = brand.get("name", "")

            # Normalize price to float
            if item["price"]:
                try:
                    item["price"] = float(str(item["price"]).replace(",", ".").replace(" ", ""))
                except (ValueError, TypeError):
                    item["price"] = None

            items.append(item)

        break  # Only process first CollectionPage

    return items


def build_search_url(base_url: str, query: str) -> str:
    """Build a tori.fi search URL from base URL and query string."""
    return f"{base_url}?q={urllib.parse.quote(query)}"


# -- Discovery logic ---------------------------------------------------------


def discover_items(
    config_path: str,
    queries: list = None,
    batch_size: int = 20,
    dry_run: bool = False,
) -> dict:
    """Run discovery: search tori.fi, extract items, dedup, add to queue.

    Returns a report dict with: searched, found, new, added, duplicates, errors
    """
    config = load_config(config_path)
    dc = get_discovery_config(config)

    if not dc["enabled"] and not queries:
        log.warning("Discovery is disabled in config and no queries provided")
        return {"error": "discovery_disabled"}

    # Determine search queries
    if queries is None:
        queries = [q.strip() for q in dc["query_hints"].split(",") if q.strip()]

    if not queries:
        log.warning("No search queries available")
        return {"error": "no_queries"}

    search_base = dc["search_base_url"]

    # Get existing URLs for dedup
    existing = get_existing_urls(config_path)
    log.info("Existing queue items: %d URLs tracked", len(existing))

    report = {
        "version": DISCOVERY_VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_path": config_path,
        "queries": queries,
        "batch_size": batch_size,
        "dry_run": dry_run,
        "searched": 0,
        "found": 0,
        "new": 0,
        "added": 0,
        "duplicates": 0,
        "errors": [],
        "items_found": [],
        "items_added": [],
    }

    all_new_items = []

    for query in queries:
        if len(all_new_items) >= batch_size:
            log.info("Batch size reached (%d), stopping search", batch_size)
            break

        search_url = build_search_url(search_base, query)
        log.info("Searching: %s", query)
        report["searched"] += 1

        try:
            html = fetch_search_page(search_url)
            items = extract_items_from_jsonld(html)
            log.info("  Found %d items in search results", len(items))
            report["found"] += len(items)

            for item in items:
                if len(all_new_items) >= batch_size:
                    break

                item_url = item["url"]
                # Check for duplicate by URL or item ID
                item_id_match = re.search(r"/item/(\d+)", item_url)
                item_id = item_id_match.group(1) if item_id_match else None

                if item_url in existing or (item_id and item_id in existing):
                    report["duplicates"] += 1
                    continue

                # New item — track it
                all_new_items.append(item)
                existing.add(item_url)
                if item_id:
                    existing.add(item_id)

                report["items_found"].append({
                    "url": item_url,
                    "name": item["name"],
                    "price": item["price"],
                })

        except Exception as e:
            error_msg = f"Search '{query}' failed: {e}"
            log.error("  %s", error_msg)
            report["errors"].append(error_msg)

        # Rate limit between searches
        if queries.index(query) < len(queries) - 1:
            time.sleep(REQUEST_DELAY)

    report["new"] = len(all_new_items)
    log.info("Discovery found %d new items (of %d total, %d duplicates)",
             report["new"], report["found"], report["duplicates"])

    # Add items to queue (unless dry run)
    if not dry_run:
        for item in all_new_items:
            try:
                if add_item_to_queue(config_path, item["url"]):
                    report["added"] += 1
                    report["items_added"].append(item["url"])
                    log.info("  Added: %s — %s", item["url"], item["name"])
                else:
                    report["errors"].append(f"Failed to add {item['url']}")
            except Exception as e:
                report["errors"].append(f"Add error for {item['url']}: {e}")
        log.info("Added %d items to queue", report["added"])
    else:
        log.info("Dry run — no items added")
        for item in all_new_items[:10]:
            log.info("  Would add: %s — %s (%.0f€)",
                     item["url"], item["name"], item["price"] or 0)

    return report


# -- CLI ---------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Discovery runner — find new items from tori.fi search",
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to queue.json",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview discovery without adding items",
    )
    parser.add_argument(
        "--query", action="append",
        help="Override search query (can be repeated). Default: use config query_hints",
    )
    parser.add_argument(
        "--batch-size", type=int,
        help="Max items to discover (default: from config)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output report as JSON",
    )

    args = parser.parse_args()

    config = load_config(args.config)
    dc = get_discovery_config(config)

    batch_size = args.batch_size or dc["batch_size"]
    queries = args.query  # None means use config

    report = discover_items(
        config_path=os.path.abspath(args.config),
        queries=queries,
        batch_size=batch_size,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n{'='*50}")
        print(f"Discovery Report")
        print(f"{'='*50}")
        print(f"Queries searched: {report.get('searched', 0)}")
        print(f"Items found:      {report.get('found', 0)}")
        print(f"Duplicates:       {report.get('duplicates', 0)}")
        print(f"New items:        {report.get('new', 0)}")
        print(f"Added to queue:   {report.get('added', 0)}")
        if report.get("errors"):
            print(f"Errors:           {len(report['errors'])}")
            for e in report["errors"]:
                print(f"  - {e}")
        if report.get("dry_run"):
            print(f"\n(Dry run — no items were added)")
        print(f"{'='*50}")


if __name__ == "__main__":
    main()
