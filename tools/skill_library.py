#!/usr/bin/env python3
"""Skill Library — catalog, discover, and install cross-project skills.

Manages a JSON catalog at ~/.config/orchestration/skill-library.json.
All commands support --json for machine-readable output.
Stdlib-only — no third-party dependencies.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CATALOG_PATH = Path.home() / ".config" / "orchestration" / "skill-library.json"
CATALOG_VERSION = 1


# ── Catalog I/O ─────────────────────────────────────────────────────────────

def _load_catalog() -> dict:
    """Load catalog from disk, or return empty skeleton."""
    if CATALOG_PATH.exists():
        with open(CATALOG_PATH) as f:
            return json.load(f)
    return {"version": CATALOG_VERSION, "skills": []}


def _save_catalog(catalog: dict) -> None:
    """Write catalog to disk, creating parent dirs if needed."""
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_PATH, "w") as f:
        json.dump(catalog, f, indent=2)
        f.write("\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Output helpers ───────────────────────────────────────────────────────────

def _output(data, *, json_mode: bool) -> None:
    """Print data as JSON or human-readable text."""
    if json_mode:
        print(json.dumps(data, indent=2))
    elif isinstance(data, str):
        print(data)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                _print_skill_row(item)
            else:
                print(item)
    elif isinstance(data, dict):
        _print_skill_detail(data)


def _print_skill_row(skill: dict) -> None:
    """One-line summary of a skill."""
    stype = skill.get("type", "?")
    domains = ", ".join(skill.get("domain", []))
    proj = skill.get("source_project", "?")
    print(f"  {skill['name']:<35} {stype:<15} {proj:<25} [{domains}]")


def _print_skill_detail(skill: dict) -> None:
    """Full detail view of a single skill."""
    print(f"Name:           {skill['name']}")
    print(f"Description:    {skill.get('description', '')}")
    print(f"Type:           {skill.get('type', '?')}")
    print(f"Domain:         {', '.join(skill.get('domain', []))}")
    print(f"Source project: {skill.get('source_project', '?')}")
    print(f"Source path:    {skill.get('source', '?')}")
    cfg = skill.get("config_required", [])
    if cfg:
        print(f"Config required: {', '.join(cfg)}")
    print(f"Last updated:   {skill.get('last_updated', '?')}")
    print(f"Cataloged at:   {skill.get('cataloged_at', '?')}")


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_catalog(args) -> None:
    """Add or update a skill in the catalog."""
    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        print(f"Error: {skill_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    catalog = _load_catalog()

    domain = [d.strip() for d in args.domain.split(",")] if args.domain else []
    config_required = (
        [c.strip() for c in args.config_required.split(",")]
        if args.config_required
        else []
    )

    # Determine last_updated from SKILL.md mtime if it exists
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        mtime = datetime.fromtimestamp(skill_md.stat().st_mtime, tz=timezone.utc)
        last_updated = mtime.strftime("%Y-%m-%d")
    else:
        last_updated = _date_today()

    # Derive source_project from path if not provided
    source_project = args.project or skill_dir.parent.parent.parent.name

    entry = {
        "name": args.name,
        "description": args.description or "",
        "source": str(skill_dir),
        "source_project": source_project,
        "domain": domain,
        "type": args.type,
        "config_required": config_required,
        "last_updated": last_updated,
        "cataloged_at": _now_iso(),
    }

    # Replace existing entry with same name, or append
    skills = catalog["skills"]
    replaced = False
    for i, s in enumerate(skills):
        if s["name"] == args.name:
            skills[i] = entry
            replaced = True
            break
    if not replaced:
        skills.append(entry)

    _save_catalog(catalog)
    action = "Updated" if replaced else "Cataloged"
    _output(
        {"status": "ok", "action": action.lower(), "skill": entry}
        if args.json
        else f"{action} skill: {args.name}",
        json_mode=args.json,
    )


def cmd_list(args) -> None:
    """List skills with optional filters."""
    catalog = _load_catalog()
    skills = catalog["skills"]

    if args.domain:
        skills = [s for s in skills if args.domain in s.get("domain", [])]
    if args.type:
        skills = [s for s in skills if s.get("type") == args.type]
    if args.project:
        skills = [s for s in skills if s.get("source_project") == args.project]

    if args.json:
        _output(skills, json_mode=True)
    else:
        if not skills:
            print("No skills found matching filters.")
            return
        print(f"{'Name':<35} {'Type':<15} {'Project':<25} Domain")
        print("-" * 90)
        _output(skills, json_mode=False)
        print(f"\n{len(skills)} skill(s)")


def cmd_search(args) -> None:
    """Search skills by keyword across name, description, and domain."""
    catalog = _load_catalog()
    keyword = args.keyword.lower()
    results = []
    for s in catalog["skills"]:
        searchable = " ".join(
            [s.get("name", ""), s.get("description", "")]
            + s.get("domain", [])
        ).lower()
        if keyword in searchable:
            results.append(s)

    if args.json:
        _output(results, json_mode=True)
    else:
        if not results:
            print(f"No skills matching '{args.keyword}'.")
            return
        print(f"{'Name':<35} {'Type':<15} {'Project':<25} Domain")
        print("-" * 90)
        _output(results, json_mode=False)
        print(f"\n{len(results)} result(s)")


def cmd_show(args) -> None:
    """Show full details of a skill."""
    catalog = _load_catalog()
    for s in catalog["skills"]:
        if s["name"] == args.skill_name:
            _output(s, json_mode=args.json)
            return
    msg = f"Skill not found: {args.skill_name}"
    if args.json:
        _output({"error": msg}, json_mode=True)
    else:
        print(msg, file=sys.stderr)
        sys.exit(1)


def cmd_install(args) -> None:
    """Install a skill into a target project's skills directory."""
    catalog = _load_catalog()
    skill = None
    for s in catalog["skills"]:
        if s["name"] == args.skill_name:
            skill = s
            break

    if skill is None:
        msg = f"Skill not found: {args.skill_name}"
        if args.json:
            _output({"error": msg}, json_mode=True)
        else:
            print(msg, file=sys.stderr)
        sys.exit(1)

    # Pattern skills cannot be installed
    if skill.get("type") == "pattern":
        msg = (
            f"Cannot install pattern-type skill '{skill['name']}'. "
            f"Use it as a reference from: {skill['source']}"
        )
        if args.json:
            _output(
                {"error": msg, "source": skill["source"], "type": "pattern"},
                json_mode=True,
            )
        else:
            print(msg)
        sys.exit(1)

    source = Path(skill["source"])
    if not source.is_dir():
        msg = f"Source path does not exist: {source}"
        if args.json:
            _output({"error": msg}, json_mode=True)
        else:
            print(msg, file=sys.stderr)
        sys.exit(1)

    target = Path(args.target).resolve() / skill["name"]

    if target.exists():
        msg = f"Target already exists: {target}"
        if args.json:
            _output({"error": msg}, json_mode=True)
        else:
            print(msg, file=sys.stderr)
        sys.exit(1)

    shutil.copytree(source, target)

    result_msg = f"Installed '{skill['name']}' to {target}"

    # Warn about config_required for configurable skills
    config_warn = None
    if skill.get("type") == "configurable" and skill.get("config_required"):
        config_warn = (
            f"This skill requires configuration: {', '.join(skill['config_required'])}. "
            f"Review the SKILL.md and configure before use."
        )

    if args.json:
        out = {"status": "ok", "installed_to": str(target), "skill": skill["name"]}
        if config_warn:
            out["warning"] = config_warn
        _output(out, json_mode=True)
    else:
        print(result_msg)
        if config_warn:
            print(f"⚠ WARNING: {config_warn}")


def cmd_sync(args) -> None:
    """Check that all source paths still exist."""
    catalog = _load_catalog()
    results = []
    valid = 0
    stale = 0

    for s in catalog["skills"]:
        source = Path(s["source"])
        exists = source.is_dir()
        results.append({
            "name": s["name"],
            "source": s["source"],
            "exists": exists,
        })
        if exists:
            valid += 1
        else:
            stale += 1

    if args.json:
        _output({"valid": valid, "stale": stale, "details": results}, json_mode=True)
    else:
        for r in results:
            status = "OK" if r["exists"] else "STALE"
            print(f"  [{status:<5}] {r['name']:<35} {r['source']}")
        print(f"\n{valid} valid, {stale} stale")


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill_library",
        description="Manage the cross-project skill catalog.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output in JSON format"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # catalog
    p_cat = sub.add_parser("catalog", help="Add/update a skill in the catalog")
    p_cat.add_argument("skill_dir", help="Path to the skill directory")
    p_cat.add_argument("--name", required=True, help="Skill name")
    p_cat.add_argument("--description", help="Short description")
    p_cat.add_argument("--domain", help="Comma-separated domain tags")
    p_cat.add_argument(
        "--type",
        required=True,
        choices=["plug-and-play", "configurable", "pattern"],
        help="Skill type",
    )
    p_cat.add_argument("--config-required", help="Comma-separated config vars")
    p_cat.add_argument("--project", help="Source project name (auto-detected if omitted)")

    # list
    p_list = sub.add_parser("list", help="List cataloged skills")
    p_list.add_argument("--domain", help="Filter by domain tag")
    p_list.add_argument("--type", choices=["plug-and-play", "configurable", "pattern"])
    p_list.add_argument("--project", help="Filter by source project")

    # search
    p_search = sub.add_parser("search", help="Search skills by keyword")
    p_search.add_argument("keyword", help="Search term")

    # show
    p_show = sub.add_parser("show", help="Show full details of a skill")
    p_show.add_argument("skill_name", help="Skill name to show")

    # install
    p_install = sub.add_parser("install", help="Install a skill into a project")
    p_install.add_argument("skill_name", help="Skill name to install")
    p_install.add_argument("--target", required=True, help="Target skills directory")

    # sync
    sub.add_parser("sync", help="Verify source paths still exist")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "catalog": cmd_catalog,
        "list": cmd_list,
        "search": cmd_search,
        "show": cmd_show,
        "install": cmd_install,
        "sync": cmd_sync,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
