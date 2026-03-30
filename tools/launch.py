#!/usr/bin/env python3
"""Unified agent launcher — launch pairs, directors, CPOs, queues, panels, planning, advisors, or observers with one command.

Replaces delegate.py (which is now a thin wrapper around this tool).

Roles:
  --role pair      Supervisor+executor pair (original delegate.py behavior)
  --role director  Director + director-subconscious sessions
  --role cpo       CPO + CPO-subconscious sessions
  --role queue     Queue operations loop (init DB + load items + director + daemon)
  --role panel     Solution discovery panel (fork + parallel personas + synthesis)
  --role planning  Planning pipeline (fork + preset-driven phase execution + brief output)
  --role advisor   Strategic Advisor (persistent exploration agent alongside CPO)
  --role observer  Passive learning observer for an existing session

Providers:
  --provider claude  Uses /loop for recurring checks (native)
  --provider codex   Uses crontab + codex_tick.py for recurring checks

Usage:
    python3 tools/launch.py --role pair --brief .cpo/briefs/x.md --branch feature/x
    python3 tools/launch.py --role director --handover .director/handover-x.md
    python3 tools/launch.py --role cpo [--skip-comms]
    python3 tools/launch.py --role queue --queue-config .operations/my-queue/queue.json
    python3 tools/launch.py --role panel --topic "How should we architect X?" --preset standard
    python3 tools/launch.py --role planning --topic "Build notification system" --preset standard
    python3 tools/launch.py --role advisor --direction .cpo/advisor/strategic-direction.md
    python3 tools/launch.py --role observer --target sup-my-task
    python3 tools/launch.py --role pair --observe --brief x.md --branch y
    python3 tools/launch.py --role pair --dry-run --brief x.md --branch y

Stdlib-only. No pip dependencies.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Optional

# Registry integration — lazy import to avoid circular deps
_registry = None
def _get_registry():
    global _registry
    if _registry is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "agent_registry", os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_registry.py"))
        _registry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_registry)
    return _registry


def _register_agent(agent_id, role, provider, tmux_session, server,
                    launched_by="launch.py", brief_ref=None):
    """Best-effort agent registration — never fails the launch."""
    try:
        reg = _get_registry()
        reg.register_agent(
            agent_id=agent_id, role=role, provider=provider,
            tmux_session=tmux_session, tmux_server=server,
            launched_by=launched_by, brief_ref=brief_ref,
        )
    except Exception:
        pass  # Registry failure must not block launch


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_NAME_MAX = 30
INIT_WAIT = {"claude": 15, "codex": 10}
VERIFY_WAIT = 5
PROVIDER_COMMANDS = {
    "claude": "claude --dangerously-skip-permissions",
    "codex": "codex --dangerously-bypass-approvals-and-sandbox",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CODEX_TICK = os.path.join(SCRIPT_DIR, "codex_tick.py")

# Crontab marker for entries managed by launch.py
CRONTAB_MARKER = "# claude-orchestration-launch:"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def derive_session_name(branch: str) -> str:
    """Derive a short session name from a branch name."""
    name = branch.rsplit("/", 1)[-1]
    return name[:SESSION_NAME_MAX]


def tmux_cmd(args: list, server: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a tmux command, optionally targeting a named server."""
    cmd = ["tmux"]
    if server:
        cmd += ["-L", server]
    cmd += args
    return subprocess.run(cmd, capture_output=True, text=True)


def log(msg: str, json_mode: bool) -> None:
    """Print a human-readable log line (suppressed in JSON mode)."""
    if not json_mode:
        print(f"  → {msg}")


def wait_for_prompt(session: str, server: Optional[str], timeout: int = 30) -> bool:
    """Wait until a session shows an idle prompt character."""
    import re
    prompt_re = re.compile(r"[›❯>]")
    elapsed = 0
    while elapsed < timeout:
        result = tmux_cmd(
            ["capture-pane", "-t", session, "-p", "-S", "-5"], server
        )
        if prompt_re.search(result.stdout):
            return True
        time.sleep(2)
        elapsed += 2
    return False


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup(sessions: list, server: Optional[str],
            worktree: Optional[str], json_mode: bool) -> None:
    """Best-effort cleanup of sessions and worktree."""
    for sess in sessions:
        if sess:
            tmux_cmd(["kill-session", "-t", sess], server)
            log(f"killed session {sess}", json_mode)

    if worktree and os.path.isdir(worktree):
        subprocess.run(
            ["git", "worktree", "remove", "--force", worktree],
            capture_output=True, text=True,
        )
        log(f"removed worktree {worktree}", json_mode)


# ---------------------------------------------------------------------------
# Crontab management for Codex tick entries
# ---------------------------------------------------------------------------

def install_crontab_entry(cron_expr: str, session: str, prompt: str,
                          server: Optional[str], entry_id: str) -> str:
    """Install a crontab entry for codex_tick.py. Returns the cron line."""
    server_flag = f" --tmux-server {server}" if server else ""
    marker = f"{CRONTAB_MARKER}{entry_id}"
    # Use absolute path to python3 and codex_tick.py
    python3 = shutil.which("python3") or "python3"
    cron_line = (
        f"{cron_expr} {python3} {CODEX_TICK} "
        f"--session {session} --prompt \"{prompt}\"{server_flag} {marker}"
    )

    # Get current crontab
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current = result.stdout if result.returncode == 0 else ""

    # Remove existing entry with same marker
    lines = [l for l in current.split("\n") if marker not in l and l.strip()]
    lines.append(cron_line)

    # Install
    subprocess.run(
        ["crontab", "-"],
        input="\n".join(lines) + "\n",
        capture_output=True, text=True,
    )
    return cron_line


def uninstall_crontab_entries(entry_id: str) -> None:
    """Remove crontab entries matching the given entry_id."""
    marker = f"{CRONTAB_MARKER}{entry_id}"
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return
    lines = [l for l in result.stdout.split("\n") if marker not in l and l.strip()]
    subprocess.run(
        ["crontab", "-"],
        input="\n".join(lines) + "\n" if lines else "",
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# Shared steps
# ---------------------------------------------------------------------------

def step_create_worktree(branch: str, worktree_path: str) -> None:
    """Create a git worktree from main onto the given branch."""
    result = subprocess.run(
        ["git", "worktree", "add", worktree_path, "-b", branch, "main"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Branch may already exist; try without -b
        result = subprocess.run(
            ["git", "worktree", "add", worktree_path, branch],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create worktree: {result.stderr.strip()}"
            )


def step_copy_brief(brief: str, worktree_path: str) -> None:
    """Generate docs/supervisor-instructions.md from base + brief in the worktree."""
    dest_dir = os.path.join(worktree_path, "docs")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "supervisor-instructions.md")
    base_path = os.path.join(PROJECT_DIR, "docs", "supervisor-instructions-base.md")
    brief_content = open(brief, "r").read()
    if os.path.isfile(base_path):
        base_content = open(base_path, "r").read()
        generated = base_content + "\n\n---\n\n# Current Brief\n\n" + brief_content
    else:
        # Fallback: use brief alone if base file is missing
        generated = brief_content
    with open(dest, "w") as f:
        f.write(generated)


def step_create_sessions(sessions: list, workdir: str,
                         server: Optional[str]) -> None:
    """Create tmux sessions."""
    for name in sessions:
        result = tmux_cmd(
            ["new-session", "-d", "-s", name, "-c", workdir], server
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create session {name}: {result.stderr.strip()}"
            )


def step_launch_provider(sessions: list, provider: str,
                         server: Optional[str]) -> None:
    """Launch the provider CLI in the given sessions."""
    cmd_str = PROVIDER_COMMANDS[provider]
    for sess in sessions:
        tmux_cmd(["send-keys", "-t", sess, cmd_str, "Enter"], server)
        time.sleep(2)
        tmux_cmd(["send-keys", "-t", sess, "Enter"], server)


def step_wait_init(provider: str) -> None:
    """Wait for agents to initialize."""
    time.sleep(INIT_WAIT[provider])


def step_inject_text(session: str, text: str, server: Optional[str]) -> None:
    """Inject text into a session via tmux send-keys -l, then Enter."""
    tmux_cmd(["send-keys", "-t", session, "-l", text], server)
    time.sleep(1)
    tmux_cmd(["send-keys", "-t", session, "Enter"], server)
    time.sleep(2)
    tmux_cmd(["send-keys", "-t", session, "Enter"], server)


def step_verify(session: str, server: Optional[str]) -> bool:
    """Verify a session is processing (not idle)."""
    time.sleep(VERIFY_WAIT)
    result = tmux_cmd(
        ["capture-pane", "-t", session, "-p", "-S", "-20"], server
    )
    output = result.stdout.strip()
    activity_signals = ["Read", "Bash", "Glob", "Grep", "Agent", "thinking",
                        "tool", "searching", "reading", "─"]
    return any(sig in output for sig in activity_signals)


def step_setup_cron(session: str, provider: str, interval: str,
                    prompt: str, server: Optional[str],
                    entry_id: str, json_mode: bool) -> Optional[str]:
    """Set up recurring checks for a session.

    For Claude: inject /loop command.
    For Codex: install crontab entry with codex_tick.py.

    Returns the cron line for Codex, or the /loop command for Claude.
    """
    if provider == "claude":
        loop_cmd = f"/loop {interval} {prompt}"
        # Wait for the session to be at a prompt before injecting /loop
        wait_for_prompt(session, server, timeout=30)
        step_inject_text(session, loop_cmd, server)
        log(f"injected /loop {interval} into {session}", json_mode)
        return loop_cmd
    else:
        # Convert interval like "15m" or "5m" to cron expression
        minutes = _parse_interval_minutes(interval)
        if minutes <= 0:
            minutes = 15
        cron_expr = f"*/{minutes} * * * *"
        cron_line = install_crontab_entry(cron_expr, session, prompt,
                                          server, entry_id)
        log(f"installed crontab ({cron_expr}) for {session}", json_mode)
        return cron_line


def _parse_interval_minutes(interval: str) -> int:
    """Parse an interval string like '15m', '30m', '1h' to minutes."""
    interval = interval.strip().lower()
    if interval.endswith("h"):
        return int(interval[:-1]) * 60
    if interval.endswith("m"):
        return int(interval[:-1])
    # Try bare number as minutes
    try:
        return int(interval)
    except ValueError:
        return 15


# ---------------------------------------------------------------------------
# Role: pair (original delegate.py)
# ---------------------------------------------------------------------------

def launch_pair(args) -> dict:
    """Launch a supervisor+executor pair."""
    brief = os.path.abspath(args.brief)
    branch = args.branch
    provider = args.provider
    server = args.tmux_server
    json_mode = args.json
    name = derive_session_name(branch)
    sup = f"sup-{name}"
    exc = f"exec-{name}"
    worktree = args.worktree_path or os.path.join("/tmp", name)

    result = {
        "status": "ok",
        "role": "pair",
        "supervisor": sup,
        "executor": exc,
        "worktree": worktree,
        "branch": branch,
        "provider": provider,
        "brief": args.brief,
    }

    # Validate
    if not os.path.isfile(brief):
        return {"status": "error", "step": "validate",
                "error": f"Brief file not found: {brief}", "cleaned_up": False}
    if provider not in PROVIDER_COMMANDS:
        return {"status": "error", "step": "validate",
                "error": f"Unknown provider: {provider}", "cleaned_up": False}

    # Dry run
    if args.dry_run:
        steps = [
            f"1. Create worktree at {worktree} on branch {branch}",
            f"2. Generate {worktree}/docs/supervisor-instructions.md from base + brief {brief}",
            f"3. Create tmux sessions: {sup}, {exc}"
            + (f" (server: {server})" if server else ""),
            f"4. Launch {provider} in both sessions: {PROVIDER_COMMANDS[provider]}",
            f"5. Wait {INIT_WAIT[provider]}s for initialization",
            f"6. Inject brief into supervisor {sup}",
            f"7. Set up supervisor 4m cron (delegation + verification reminders)",
            f"8. Verify supervisor is processing",
        ]
        if args.observe:
            obs_run_id = _generate_observer_run_id(args.run_id)
            obs_report = _derive_observer_report_path(obs_run_id, args.report_path)
            obs_sess = f"obs-{sup}"[:SESSION_NAME_MAX]
            steps += [
                f"8. Create observer session: {obs_sess} (target: {sup})",
                f"9. Launch {provider} in observer, inject brief (run: {obs_run_id})",
                f"10. Set up 10m observer cron, register in agent + observer registries",
                f"11. Observer report: {obs_report}",
            ]
        if json_mode:
            result["status"] = "dry_run"
            result["steps"] = steps
            return result
        print("Dry run — would execute:")
        for s in steps:
            print(f"  {s}")
        return {"status": "dry_run"}

    # Execute
    created_worktree = False
    created_sessions = False

    try:
        log(f"creating worktree at {worktree} on branch {branch}", json_mode)
        step_create_worktree(branch, worktree)
        created_worktree = True

        log("generating supervisor-instructions.md from base + brief", json_mode)
        step_copy_brief(brief, worktree)

        log(f"creating tmux sessions {sup} and {exc}", json_mode)
        step_create_sessions([sup, exc], worktree, server)
        created_sessions = True

        log(f"launching {provider} in both sessions", json_mode)
        step_launch_provider([exc, sup], provider, server)

        log(f"waiting {INIT_WAIT[provider]}s for initialization", json_mode)
        step_wait_init(provider)

        # Determine verification level
        vlevel = getattr(args, 'verification_level', None)
        vlevel_str = f"Level {vlevel}" if vlevel else "Level 2+"
        vlevel_desc = {
            2: "App starts and health check passes",
            3: "Core user flow completes end-to-end",
            4: "Edge cases and error paths tested",
        }.get(vlevel, "App starts and health check passes (minimum)")

        log("injecting brief into supervisor", json_mode)
        prompt = (
            f"Read docs/supervisor-instructions.md for your complete task brief. "
            f"You are a SUPERVISOR — you DELEGATE, you do NOT implement. "
            f"Your executor is in tmux session '{exc}'. "
            f"FIRST: send the task brief to your executor via tmux send-keys. "
            f"THEN: monitor the executor's progress, verify its output, "
            f"and when done: commit, push, create a PR with `gh pr create`, "
            f"and state 'WORK COMPLETE — PR created, ready for review'. "
            f"VERIFICATION REQUIRED: {vlevel_str} — {vlevel_desc}. "
            f"Run the smoke-test script before declaring done."
        )
        step_inject_text(sup, prompt, server)

        # Set up supervisor cron — recurring check every 4 minutes
        log("setting up supervisor 4m cron", json_mode)
        sup_cron_prompt = (
            f"Supervisor 4-min check: "
            f"(1) Did you brief the executor (session '{exc}')? If not, do it NOW. "
            f"(2) Is the executor working or stalled? `tmux capture-pane -t {exc} -p -S -10` "
            f"(3) {vlevel_str} VERIFICATION REQUIRED ({vlevel_desc}). "
            f"Has the smoke-test been run? Check: `ls scripts/smoke-test-*.sh 2>/dev/null` — if it exists, RUN IT. "
            f"Check: `ls evidence/` — if no evidence, verification is incomplete. "
            f"(4) 'Build passes' is NOT sufficient for WORK COMPLETE."
        )
        step_setup_cron(sup, provider, "4m", sup_cron_prompt,
                        server, f"sup-{name}", json_mode)

        log("verifying supervisor is active", json_mode)
        active = step_verify(sup, server)
        if not active:
            log("warning: supervisor may not have started processing yet",
                json_mode)
            result["warning"] = "supervisor activity not confirmed"

        # Register agents in registry
        brief_rel = os.path.relpath(brief, worktree) if brief else None
        _register_agent(sup, "supervisor", provider, sup, server,
                        brief_ref=brief_rel)
        _register_agent(exc, "executor", provider, exc, server,
                        brief_ref=brief_rel)

        # Spawn observer if --observe is set
        if args.observe:
            _launch_observer_for_target(sup, args, result)

        log("delegation complete", json_mode)
        return result

    except Exception as e:
        step_name = "unknown"
        if not created_worktree:
            step_name = "create_worktree"
        elif not created_sessions:
            step_name = "create_sessions"
        else:
            step_name = "launch_provider"

        log(f"error at {step_name}: {e}", json_mode)
        cleanup(
            [sup if created_sessions else None,
             exc if created_sessions else None],
            server,
            worktree if created_worktree else None,
            json_mode,
        )
        return {"status": "error", "step": step_name,
                "error": str(e), "cleaned_up": True}


# ---------------------------------------------------------------------------
# Role: director
# ---------------------------------------------------------------------------

# Default prompts for director cron cycles
DIRECTOR_CRON_PROMPT = (
    "Director recurring check. Read .director/registry.json and run one "
    "monitoring cycle: check each executing project's supervisor pane, "
    "detect completions or stalls, merge completed work, and launch queued "
    "projects. Update registry.json with timestamps."
)
DIRECTOR_SUB_CRON_PROMPT = (
    "Subconscious cycle. Base yourself on .cpo/subconsciousness-brief.md. "
    "Run exactly one monitoring cycle: inspect the director session, inspect "
    "active sup-/exec- sessions, intervene on blocking dialogs if present, "
    "and send at most one short [subconscious] pulse only if it materially helps."
)


def launch_director(args) -> dict:
    """Launch a director + director-subconscious pair."""
    provider = args.provider
    server = args.tmux_server
    json_mode = args.json
    handover = os.path.abspath(args.handover) if args.handover else None

    dir_session = "director"
    sub_session = "director-subconscious"
    workdir = PROJECT_DIR

    result = {
        "status": "ok",
        "role": "director",
        "director": dir_session,
        "subconscious": sub_session,
        "provider": provider,
    }

    # Validate
    if handover and not os.path.isfile(handover):
        return {"status": "error", "step": "validate",
                "error": f"Handover file not found: {handover}",
                "cleaned_up": False}

    # Dry run
    if args.dry_run:
        steps = [
            f"1. Create tmux sessions: {dir_session}, {sub_session}"
            + (f" (server: {server})" if server else ""),
            f"2. Launch {provider} in both sessions",
            f"3. Wait {INIT_WAIT[provider]}s for initialization",
        ]
        if handover:
            steps.append(f"4. Inject handover ({handover}) into {dir_session}")
        else:
            steps.append(f"4. (no handover file — director starts fresh)")
        steps += [
            f"5. Inject subconscious brief into {sub_session}",
            f"6. Set up recurring checks — director: 15m, subconscious: 5m"
            + (f" (via /loop)" if provider == "claude" else " (via crontab)"),
            f"7. Verify both sessions active",
        ]
        if args.observe:
            obs_run_id = _generate_observer_run_id(getattr(args, "run_id", None))
            obs_report = _derive_observer_report_path(obs_run_id, getattr(args, "report_path", None))
            obs_sess = f"obs-{dir_session}"[:SESSION_NAME_MAX]
            steps += [
                f"8. Create observer session: {obs_sess} (target: {dir_session})",
                f"9. Launch {provider} in observer, inject brief (run: {obs_run_id})",
                f"10. Set up 10m observer cron, register in agent + observer registries",
                f"11. Observer report: {obs_report}",
            ]
        if json_mode:
            result["status"] = "dry_run"
            result["steps"] = steps
            return result
        print("Dry run — would execute:")
        for s in steps:
            print(f"  {s}")
        return {"status": "dry_run"}

    # Execute
    created_sessions = False
    try:
        log(f"creating tmux sessions {dir_session} and {sub_session}", json_mode)
        step_create_sessions([dir_session, sub_session], workdir, server)
        created_sessions = True

        log(f"launching {provider} in both sessions", json_mode)
        step_launch_provider([dir_session, sub_session], provider, server)

        log(f"waiting {INIT_WAIT[provider]}s for initialization", json_mode)
        step_wait_init(provider)

        # Inject handover into director
        if handover:
            log(f"injecting handover into {dir_session}", json_mode)
            handover_prompt = (
                f"Read {os.path.relpath(handover, PROJECT_DIR)} for your "
                f"handover context, then read .director/director-instructions.md "
                f"for your operating procedures. You are a director — you "
                f"orchestrate supervisor+executor pairs. Start your monitoring "
                f"loop and check registry.json for active projects."
            )
            step_inject_text(dir_session, handover_prompt, server)
        else:
            log(f"injecting startup prompt into {dir_session}", json_mode)
            startup_prompt = (
                "Read .director/director-instructions.md for your operating "
                "procedures. You are a director — you orchestrate supervisor+"
                "executor pairs. Start your monitoring loop and check "
                "registry.json for active projects."
            )
            step_inject_text(dir_session, startup_prompt, server)

        # Inject subconscious brief
        log(f"injecting subconscious brief into {sub_session}", json_mode)
        sub_prompt = (
            f"Read .cpo/subconsciousness-brief.md for your operating procedures. "
            f"You are the director-subconscious. Your target session is "
            f"'{dir_session}'. Run monitoring cycles to detect stalls and "
            f"intervene when needed."
        )
        step_inject_text(sub_session, sub_prompt, server)

        # Set up recurring checks
        log("setting up recurring checks", json_mode)
        step_setup_cron(dir_session, provider, "15m", DIRECTOR_CRON_PROMPT,
                        server, "director-main", json_mode)
        step_setup_cron(sub_session, provider, "5m", DIRECTOR_SUB_CRON_PROMPT,
                        server, "director-sub", json_mode)

        # Verify
        log("verifying director is active", json_mode)
        active = step_verify(dir_session, server)
        if not active:
            log("warning: director may not have started processing yet",
                json_mode)
            result["warning"] = "director activity not confirmed"

        # Register agents in registry
        handover_rel = os.path.relpath(handover, PROJECT_DIR) if handover else None
        _register_agent(dir_session, "director", provider, dir_session, server,
                        brief_ref=handover_rel)
        _register_agent(sub_session, "subconscious", provider, sub_session, server)

        # Spawn observer if --observe is set
        if args.observe:
            _launch_observer_for_target(dir_session, args, result)

        log("director launch complete", json_mode)
        return result

    except Exception as e:
        log(f"error: {e}", json_mode)
        cleanup(
            [dir_session if created_sessions else None,
             sub_session if created_sessions else None],
            server, None, json_mode,
        )
        return {"status": "error", "step": "launch_director",
                "error": str(e), "cleaned_up": True}


# ---------------------------------------------------------------------------
# Role: cpo
# ---------------------------------------------------------------------------

CPO_CRON_PROMPT = (
    "CPO recurring 30-minute check. Read .cpo/checks/check-30min.md and run "
    "one quick status cycle. Review active supervisor/executor sessions, "
    "blockers, watchdog/comms state if relevant, and continue in-progress "
    "work rather than idling. If no concrete work is active, pick the "
    "highest-ROI non-overlapping support task."
)
CPO_SUB_CRON_PROMPT = (
    "Subconscious cycle. Base yourself on .cpo/subconsciousness-brief.md. "
    "Run exactly one monitoring cycle: inspect the CPO session, inspect "
    "active sup-/exec- sessions, intervene on blocking dialogs if present, "
    "and send at most one short [subconscious] pulse only if it materially helps."
)

OBSERVER_CRON_PROMPT = (
    "Observer cycle. Read .cpo/observer-brief.md for procedures. "
    "Run one observation cycle: capture target session pane, "
    "check for completion signals, update your running notes. "
    "If target is gone or WORK COMPLETE detected, write final report "
    "and output OBSERVATION COMPLETE."
)


def launch_cpo(args) -> dict:
    """Launch a CPO + CPO-subconscious pair."""
    provider = args.provider
    server = args.tmux_server
    json_mode = args.json
    skip_comms = args.skip_comms

    cpo_session = "cpo"
    sub_session = "cpo-subconscious"
    workdir = PROJECT_DIR

    result = {
        "status": "ok",
        "role": "cpo",
        "cpo": cpo_session,
        "subconscious": sub_session,
        "provider": provider,
        "comms_enabled": not skip_comms,
    }

    # Dry run
    if args.dry_run:
        steps = [
            f"1. Create tmux sessions: {cpo_session}, {sub_session}"
            + (f" (server: {server})" if server else ""),
            f"2. Launch {provider} in both sessions",
            f"3. Wait {INIT_WAIT[provider]}s for initialization",
            f"4. Inject CPO initial brief into {cpo_session}",
            f"5. Inject subconscious brief into {sub_session}",
            f"6. Set up recurring checks — CPO: 30m, subconscious: 10m"
            + (f" (via /loop)" if provider == "claude" else " (via crontab)"),
        ]
        if not skip_comms:
            steps.append("7. Enable Telegram poller")
        else:
            steps.append("7. (skipping comms setup)")
        steps.append(f"8. Verify both sessions active")
        if args.observe:
            obs_run_id = _generate_observer_run_id(getattr(args, "run_id", None))
            obs_report = _derive_observer_report_path(obs_run_id, getattr(args, "report_path", None))
            obs_sess = f"obs-{cpo_session}"[:SESSION_NAME_MAX]
            steps += [
                f"9. Create observer session: {obs_sess} (target: {cpo_session})",
                f"10. Launch {provider} in observer, inject brief (run: {obs_run_id})",
                f"11. Set up 10m observer cron, register in agent + observer registries",
                f"12. Observer report: {obs_report}",
            ]
        if json_mode:
            result["status"] = "dry_run"
            result["steps"] = steps
            return result
        print("Dry run — would execute:")
        for s in steps:
            print(f"  {s}")
        return {"status": "dry_run"}

    # Execute
    created_sessions = False
    try:
        log(f"creating tmux sessions {cpo_session} and {sub_session}", json_mode)
        step_create_sessions([cpo_session, sub_session], workdir, server)
        created_sessions = True

        log(f"launching {provider} in both sessions", json_mode)
        step_launch_provider([cpo_session, sub_session], provider, server)

        log(f"waiting {INIT_WAIT[provider]}s for initialization", json_mode)
        step_wait_init(provider)

        # Inject CPO brief
        log(f"injecting CPO brief into {cpo_session}", json_mode)
        cpo_prompt = (
            "Read CLAUDE.md for project context and your operating procedures. "
            "You are the CPO (Chief Project Orchestrator). Read "
            ".cpo/cpo-routine.md for your routine, then read "
            ".cpo/checks/cron-prompts.md and set up your cron loops. "
            "Read .cpo/lifecycle.md for the current project stage — before creating "
            "any briefs, verify the work is appropriate for the current stage. "
            "Start by reading .cpo/daily-todo.md for today's priorities."
        )
        step_inject_text(cpo_session, cpo_prompt, server)

        # Inject subconscious brief
        log(f"injecting subconscious brief into {sub_session}", json_mode)
        sub_prompt = (
            f"Read .cpo/subconsciousness-brief.md for your operating procedures. "
            f"You are the CPO-subconscious. Your target session is "
            f"'{cpo_session}'. Run monitoring cycles to detect stalls and "
            f"intervene when needed."
        )
        step_inject_text(sub_session, sub_prompt, server)

        # Set up recurring checks
        log("setting up recurring checks", json_mode)
        step_setup_cron(cpo_session, provider, "30m", CPO_CRON_PROMPT,
                        server, "cpo-main", json_mode)
        step_setup_cron(sub_session, provider, "10m", CPO_SUB_CRON_PROMPT,
                        server, "cpo-sub", json_mode)

        # Enable comms
        if not skip_comms:
            log("enabling Telegram poller", json_mode)
            poller_script = os.path.join(SCRIPT_DIR, "run_telegram_poller.sh")
            if os.path.isfile(poller_script):
                subprocess.Popen(
                    ["bash", poller_script],
                    cwd=PROJECT_DIR,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log("Telegram poller started", json_mode)
            else:
                log("warning: run_telegram_poller.sh not found, skipping comms",
                    json_mode)
                result["warning"] = "Telegram poller script not found"
        else:
            log("skipping comms setup (--skip-comms)", json_mode)

        # Verify
        log("verifying CPO is active", json_mode)
        active = step_verify(cpo_session, server)
        if not active:
            log("warning: CPO may not have started processing yet", json_mode)
            result.setdefault("warning", "")
            if result["warning"]:
                result["warning"] += "; CPO activity not confirmed"
            else:
                result["warning"] = "CPO activity not confirmed"

        # Register agents in registry
        _register_agent(cpo_session, "cpo", provider, cpo_session, server)
        _register_agent(sub_session, "subconscious", provider, sub_session, server)

        # Spawn observer if --observe is set
        if args.observe:
            _launch_observer_for_target(cpo_session, args, result)

        log("CPO launch complete", json_mode)
        return result

    except Exception as e:
        log(f"error: {e}", json_mode)
        cleanup(
            [cpo_session if created_sessions else None,
             sub_session if created_sessions else None],
            server, None, json_mode,
        )
        return {"status": "error", "step": "launch_cpo",
                "error": str(e), "cleaned_up": True}


# ---------------------------------------------------------------------------
# Role: observer
# ---------------------------------------------------------------------------

def _generate_observer_run_id(explicit_run_id: Optional[str] = None) -> str:
    """Generate an observer run ID like obs-20260328-162800."""
    if explicit_run_id:
        return explicit_run_id
    return f"obs-{time.strftime('%Y%m%d-%H%M%S')}"


def _derive_observer_report_path(run_id: str,
                                 explicit_path: Optional[str] = None) -> str:
    """Derive the observer report path."""
    if explicit_path:
        return explicit_path
    return os.path.join(".cpo", "observations", f"{run_id}-obs.md")


def _build_observer_prompt(target_session: str, run_id: str,
                           report_path: str,
                           focus: Optional[str] = None) -> str:
    """Build the observer startup prompt."""
    prompt = (
        f"Read .cpo/observer-brief.md for your operating procedures. "
        f"You are an observer for session '{target_session}'. "
        f"Your run ID is '{run_id}'. "
        f"Write your report to '{report_path}'."
    )
    if focus:
        prompt += f" Focus area: {focus}."
    prompt += " Begin observing immediately."
    return prompt


def _register_observer_entry(run_id: str, target_session: str,
                             report_path: str) -> None:
    """Add an entry to .cpo/observations/registry.json via observer_registry.py."""
    try:
        entry = json.dumps({
            "id": run_id,
            "run_id": run_id,
            "target_session": target_session,
            "report_path": report_path,
            "status": "pending",
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "observer_registry.py"),
             "add", entry],
            capture_output=True, text=True,
        )
    except Exception:
        pass  # Observer registry failure must not block launch


def _launch_observer_for_target(target_session: str, args,
                                result: dict) -> Optional[str]:
    """Shared helper: spawn an observer session for a given target.

    Returns the observer session name on success, None on failure.
    Adds observer info to result dict. Never raises — observer launch
    failure is a warning, not a fatal error.
    """
    server = args.tmux_server
    provider = args.provider
    json_mode = args.json
    focus = getattr(args, "observer_focus", None)

    run_id = _generate_observer_run_id(getattr(args, "run_id", None))
    report_path = _derive_observer_report_path(
        run_id, getattr(args, "report_path", None))
    obs_session = f"obs-{target_session}"[:SESSION_NAME_MAX]

    try:
        # Ensure observations directory exists
        obs_dir = os.path.join(PROJECT_DIR, ".cpo", "observations")
        os.makedirs(obs_dir, exist_ok=True)

        log(f"creating observer session {obs_session} for target {target_session}",
            json_mode)
        step_create_sessions([obs_session], PROJECT_DIR, server)

        log(f"launching {provider} in observer session", json_mode)
        step_launch_provider([obs_session], provider, server)

        log(f"waiting {INIT_WAIT[provider]}s for observer initialization",
            json_mode)
        step_wait_init(provider)

        # Inject observer startup prompt
        prompt = _build_observer_prompt(target_session, run_id,
                                        report_path, focus)
        log("injecting observer brief", json_mode)
        step_inject_text(obs_session, prompt, server)

        # Set up 10-minute cron for observer
        log("setting up observer recurring checks (10m)", json_mode)
        step_setup_cron(obs_session, provider, "10m", OBSERVER_CRON_PROMPT,
                        server, f"observer-{run_id}", json_mode)

        # Register in agent registry
        _register_agent(obs_session, "observer", provider, obs_session, server,
                        brief_ref=".cpo/observer-brief.md")

        # Register in observer registry
        _register_observer_entry(run_id, target_session, report_path)

        # Add observer info to result
        result["observer"] = obs_session
        result["observer_run_id"] = run_id
        result["observer_report"] = report_path

        log(f"observer {obs_session} launched (run: {run_id})", json_mode)
        return obs_session

    except Exception as e:
        log(f"warning: observer launch failed: {e}", json_mode)
        result.setdefault("warning", "")
        if result.get("warning"):
            result["warning"] += f"; observer launch failed: {e}"
        else:
            result["warning"] = f"observer launch failed: {e}"
        return None


def launch_observer(args) -> dict:
    """Launch a standalone observer for an already-running session."""
    target = args.target
    provider = args.provider
    server = args.tmux_server
    json_mode = args.json
    focus = args.observer_focus

    run_id = _generate_observer_run_id(args.run_id)
    report_path = _derive_observer_report_path(run_id, args.report_path)
    obs_session = f"obs-{target}"[:SESSION_NAME_MAX]

    result = {
        "status": "ok",
        "role": "observer",
        "observer": obs_session,
        "target": target,
        "run_id": run_id,
        "report_path": report_path,
        "provider": provider,
    }

    # Dry run
    if args.dry_run:
        steps = [
            f"1. Validate target session '{target}' exists",
            f"2. Generate run-id: {run_id}",
            f"3. Report path: {report_path}",
            f"4. Create observer tmux session: {obs_session}"
            + (f" (server: {server})" if server else ""),
            f"5. Launch {provider} in observer session: {PROVIDER_COMMANDS[provider]}",
            f"6. Wait {INIT_WAIT[provider]}s for initialization",
            f"7. Inject observer startup prompt into {obs_session}",
            f"8. Set up 10-minute recurring cron for observer",
            f"9. Register in agent registry (role=observer)",
            f"10. Add entry to .cpo/observations/registry.json",
        ]
        if focus:
            steps.append(f"11. Custom focus: {focus}")
        if json_mode:
            result["status"] = "dry_run"
            result["steps"] = steps
            return result
        print("Dry run — would execute:")
        for s in steps:
            print(f"  {s}")
        return {"status": "dry_run"}

    # Validate target session exists
    check = tmux_cmd(["has-session", "-t", target], server)
    if check.returncode != 0:
        return {"status": "error", "step": "validate",
                "error": f"Target session '{target}' does not exist",
                "cleaned_up": False}

    # Ensure observations directory exists
    obs_dir = os.path.join(PROJECT_DIR, ".cpo", "observations")
    os.makedirs(obs_dir, exist_ok=True)

    created_session = False
    try:
        log(f"creating observer session {obs_session}", json_mode)
        step_create_sessions([obs_session], PROJECT_DIR, server)
        created_session = True

        log(f"launching {provider} in observer session", json_mode)
        step_launch_provider([obs_session], provider, server)

        log(f"waiting {INIT_WAIT[provider]}s for initialization", json_mode)
        step_wait_init(provider)

        # Inject observer startup prompt
        prompt = _build_observer_prompt(target, run_id, report_path, focus)
        log("injecting observer brief", json_mode)
        step_inject_text(obs_session, prompt, server)

        # Set up 10-minute cron
        log("setting up observer recurring checks (10m)", json_mode)
        step_setup_cron(obs_session, provider, "10m", OBSERVER_CRON_PROMPT,
                        server, f"observer-{run_id}", json_mode)

        # Verify
        log("verifying observer is active", json_mode)
        active = step_verify(obs_session, server)
        if not active:
            log("warning: observer may not have started processing yet",
                json_mode)
            result["warning"] = "observer activity not confirmed"

        # Register in agent registry
        _register_agent(obs_session, "observer", provider, obs_session, server,
                        brief_ref=".cpo/observer-brief.md")

        # Register in observer registry
        _register_observer_entry(run_id, target, report_path)

        log(f"observer launch complete (run: {run_id})", json_mode)
        return result

    except Exception as e:
        log(f"error: {e}", json_mode)
        if created_session:
            cleanup([obs_session], server, None, json_mode)
        return {"status": "error", "step": "launch_observer",
                "error": str(e), "cleaned_up": created_session}


# ---------------------------------------------------------------------------
# Role: queue
# ---------------------------------------------------------------------------

QUEUE_RUNNER = os.path.join(SCRIPT_DIR, "queue_runner.py")
QUEUE_DAEMON = os.path.join(SCRIPT_DIR, "queue_daemon.py")


def launch_queue(args) -> dict:
    """Launch a complete queue operations loop.

    Steps:
    1. Initialize the queue database
    2. Add items from --items-file (if provided)
    3. Launch Queue Director session + subconscious (unless --skip-director)
    4. Inject queue-director-handover into director
    5. Start the queue daemon in a tmux session
    6. Register all sessions with agent registry
    7. Verify: director alive, daemon alive, queue initialized
    """
    queue_config = os.path.abspath(args.queue_config)
    provider = args.provider
    server = args.tmux_server
    json_mode = args.json
    items_file = os.path.abspath(args.items_file) if args.items_file else None
    learning_mode = args.learning_mode
    daemon_mode = args.daemon_mode or "passive"
    skip_director = args.skip_director

    # Validate
    if not os.path.isfile(queue_config):
        return {"status": "error", "step": "validate",
                "error": f"Queue config not found: {queue_config}",
                "cleaned_up": False}
    if items_file and not os.path.isfile(items_file):
        return {"status": "error", "step": "validate",
                "error": f"Items file not found: {items_file}",
                "cleaned_up": False}

    # Load config
    with open(queue_config) as f:
        config = json.load(f)
    queue_id = config.get("queue_id", "unknown")
    queue_dir = os.path.dirname(queue_config)

    # Resolve handover path (co-located with queue.json)
    handover_path = os.path.join(queue_dir, "queue-director-handover.md")

    # Session names
    daemon_session = f"queue-daemon-{queue_id}"
    dir_session = "director"
    sub_session = "director-subconscious"

    result = {
        "status": "ok",
        "role": "queue",
        "queue_id": queue_id,
        "provider": provider,
        "daemon": daemon_session,
        "daemon_mode": daemon_mode,
    }
    if not skip_director:
        result["director"] = dir_session
    if learning_mode:
        result["learning_mode"] = learning_mode

    # Dry run
    if args.dry_run:
        steps = [
            f"1. Initialize queue DB: queue_runner.py init --config {queue_config}",
        ]
        if items_file:
            steps.append(
                f"2. Add items: queue_runner.py add --config {queue_config} "
                f"--batch-file {items_file}"
            )
        else:
            steps.append("2. (no --items-file — skip batch loading)")
        if not skip_director:
            steps += [
                f"3. Create tmux sessions: {dir_session}, {sub_session}"
                + (f" (server: {server})" if server else ""),
                f"4. Launch {provider} in director sessions",
                f"5. Inject queue-director-handover into {dir_session}",
            ]
        else:
            steps += [
                "3. (--skip-director — no director sessions)",
                "4. (--skip-director — no provider launch)",
                "5. (--skip-director — no handover injection)",
            ]
        daemon_cmd = (
            f"python3 tools/queue_daemon.py --config {queue_config} run"
        )
        if daemon_mode != "passive":
            daemon_cmd += f" --mode {daemon_mode}"
        steps.append(
            f"6. Start daemon in tmux session {daemon_session}: {daemon_cmd}"
        )
        steps.append("7. Register sessions with agent registry")
        steps.append("8. Verify: director alive, daemon alive, queue initialized")
        if json_mode:
            result["status"] = "dry_run"
            result["steps"] = steps
            return result
        print("Dry run — would execute:")
        for s in steps:
            print(f"  {s}")
        return {"status": "dry_run"}

    # Execute
    created_director = False
    created_daemon = False
    items_loaded = 0

    try:
        # Step 1: Initialize queue DB
        log(f"initializing queue DB for {queue_id}", json_mode)
        init_result = subprocess.run(
            [sys.executable, QUEUE_RUNNER, "init",
             "--config", queue_config, "--force"],
            capture_output=True, text=True,
        )
        if init_result.returncode != 0:
            raise RuntimeError(
                f"queue_runner init failed: {init_result.stderr.strip() or init_result.stdout.strip()}"
            )
        log(init_result.stdout.strip(), json_mode)

        # Step 2: Add items from --items-file
        if items_file:
            log(f"loading items from {items_file}", json_mode)
            add_result = subprocess.run(
                [sys.executable, QUEUE_RUNNER, "add",
                 "--config", queue_config, "--batch-file", items_file],
                capture_output=True, text=True,
            )
            if add_result.returncode != 0:
                raise RuntimeError(
                    f"queue_runner add failed: {add_result.stderr.strip() or add_result.stdout.strip()}"
                )
            log(add_result.stdout.strip(), json_mode)
            # Parse count from output like "Added 15 item(s) to queue."
            for word in add_result.stdout.split():
                if word.isdigit():
                    items_loaded = int(word)
                    break
        else:
            log("no --items-file provided, skipping batch load", json_mode)

        # Query queue status for result
        status_result = subprocess.run(
            [sys.executable, QUEUE_RUNNER, "status",
             "--config", queue_config, "--json"],
            capture_output=True, text=True,
        )
        if status_result.returncode == 0:
            try:
                counts = json.loads(status_result.stdout)
                result["items_loaded"] = items_loaded
                result["items_ready"] = counts.get("ready", 0)
            except json.JSONDecodeError:
                result["items_loaded"] = items_loaded

        # Step 3-4: Launch director (unless --skip-director)
        if not skip_director:
            log(f"creating tmux sessions {dir_session} and {sub_session}",
                json_mode)
            step_create_sessions([dir_session, sub_session], PROJECT_DIR,
                                 server)
            created_director = True

            log(f"launching {provider} in director sessions", json_mode)
            step_launch_provider([dir_session, sub_session], provider, server)

            log(f"waiting {INIT_WAIT[provider]}s for initialization",
                json_mode)
            step_wait_init(provider)

            # Inject handover into director
            if os.path.isfile(handover_path):
                log(f"injecting queue-director-handover into {dir_session}",
                    json_mode)
                handover_rel = os.path.relpath(handover_path, PROJECT_DIR)
                handover_prompt = (
                    f"Read {handover_rel} for your handover context, then read "
                    f".director/director-instructions.md for your operating "
                    f"procedures. You are a queue director — you orchestrate "
                    f"workers processing items from the {queue_id} queue. "
                    f"Start your monitoring loop."
                )
                step_inject_text(dir_session, handover_prompt, server)
            else:
                log(f"warning: handover not found at {handover_path}, "
                    f"starting director fresh", json_mode)
                startup_prompt = (
                    f"Read .director/director-instructions.md for your "
                    f"operating procedures. You are a queue director for the "
                    f"{queue_id} queue. Config: {os.path.relpath(queue_config, PROJECT_DIR)}. "
                    f"Start your monitoring loop."
                )
                step_inject_text(dir_session, startup_prompt, server)

            # Inject subconscious brief
            log(f"injecting subconscious brief into {sub_session}", json_mode)
            sub_prompt = (
                f"Read .cpo/subconsciousness-brief.md for your operating "
                f"procedures. You are the director-subconscious. Your target "
                f"session is '{dir_session}'. Run monitoring cycles to detect "
                f"stalls and intervene when needed."
            )
            step_inject_text(sub_session, sub_prompt, server)

            # Set up recurring checks for director
            log("setting up director recurring checks", json_mode)
            step_setup_cron(dir_session, provider, "15m",
                            DIRECTOR_CRON_PROMPT, server,
                            "director-main", json_mode)
            step_setup_cron(sub_session, provider, "5m",
                            DIRECTOR_SUB_CRON_PROMPT, server,
                            "director-sub", json_mode)
        else:
            log("skipping director launch (--skip-director)", json_mode)

        # Step 5: Start queue daemon in tmux session
        log(f"starting queue daemon in session {daemon_session}", json_mode)
        if os.path.isfile(QUEUE_DAEMON):
            step_create_sessions([daemon_session], PROJECT_DIR, server)
            created_daemon = True
            daemon_cmd = (
                f"python3 {QUEUE_DAEMON} --config {queue_config} run"
            )
            if daemon_mode != "passive":
                daemon_cmd += f" --mode {daemon_mode}"
            if learning_mode:
                daemon_cmd += f" --learning-mode {learning_mode}"
            tmux_cmd(["send-keys", "-t", daemon_session, daemon_cmd, "Enter"],
                     server)
            log("queue daemon started", json_mode)
        else:
            log("warning: queue_daemon.py not found, skipping daemon start",
                json_mode)
            result["warning"] = "queue_daemon.py not found — daemon not started"

        # Step 6: Register sessions
        log("registering agents", json_mode)
        config_rel = os.path.relpath(queue_config, PROJECT_DIR)
        if not skip_director:
            _register_agent(dir_session, "queue-director", provider,
                            dir_session, server, brief_ref=config_rel)
            _register_agent(sub_session, "subconscious", provider,
                            sub_session, server)
        if created_daemon:
            _register_agent(daemon_session, "queue-daemon", "system",
                            daemon_session, server, brief_ref=config_rel)

        # Step 7: Verify
        log("verifying launch", json_mode)
        if not skip_director:
            active = step_verify(dir_session, server)
            if not active:
                log("warning: director may not have started processing yet",
                    json_mode)
                result.setdefault("warning", "")
                if result.get("warning"):
                    result["warning"] += "; director activity not confirmed"
                else:
                    result["warning"] = "director activity not confirmed"

        if created_daemon:
            # Check daemon session exists
            check = tmux_cmd(["has-session", "-t", daemon_session], server)
            if check.returncode != 0:
                log("warning: daemon session not found", json_mode)
                result.setdefault("warning", "")
                if result.get("warning"):
                    result["warning"] += "; daemon session not found"
                else:
                    result["warning"] = "daemon session not found"

        log("queue launch complete", json_mode)
        return result

    except Exception as e:
        log(f"error: {e}", json_mode)
        sessions_to_clean = []
        if created_director:
            sessions_to_clean += [dir_session, sub_session]
        if created_daemon:
            sessions_to_clean.append(daemon_session)
        cleanup(sessions_to_clean, server, None, json_mode)
        return {"status": "error", "step": "launch_queue",
                "error": str(e), "cleaned_up": True}


# ---------------------------------------------------------------------------
# Role: planning
# ---------------------------------------------------------------------------

PLANNING_PRESETS = {
    "light": {
        "phases": ["Phase 1: Scope definition", "Phase 5: Split into briefs"],
        "default_model": "haiku",
        "model_id": "claude-haiku-4-5-20251001",
        "budget_minutes": 15,
        "embed_panel": False,
    },
    "standard": {
        "phases": [
            "Phase 0: Prerequisites audit",
            "Phase 0.5: Human setup gate",
            "Phase 0.7: Verification capability check",
            "Phase 1: Scope definition",
            "Phase 2: Research",
            "Phase 3: Architecture decisions",
            "Phase 4: Phasing and dependencies",
            "Phase 5: Split into briefs",
        ],
        "default_model": "sonnet",
        "model_id": "claude-sonnet-4-6",
        "budget_minutes": 45,
        "embed_panel": False,
    },
    "deep": {
        "phases": [
            "Phase 0: Prerequisites audit",
            "Phase 0.5: Human setup gate",
            "Phase 0.7: Verification capability check",
            "Phase 1: Scope definition",
            "Phase 2: Research (with embedded panel)",
            "Phase 3: Architecture decisions",
            "Phase 4: Phasing and dependencies",
            "Phase 5: Split into briefs",
            "Phase 6: Integration planning",
            "Phase 7: E2E test planning",
        ],
        "default_model": "opus",
        "model_id": "claude-opus-4-6",
        "budget_minutes": 90,
        "embed_panel": True,
    },
}

MODEL_IDS = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}


def _build_planning_prompt(run_id: str, topic: str, preset: str,
                           config: dict) -> str:
    """Build the planning agent instruction prompt."""
    preset_cfg = PLANNING_PRESETS[preset]
    phases = preset_cfg["phases"]
    budget = preset_cfg["budget_minutes"]

    phase_list = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(phases))

    prompt = (
        f"You are a Planning Agent for run '{run_id}'.\n\n"
        f"## Your Task\n\n"
        f"Read `.planning/{run_id}/topic.md` for the planning topic. "
        f"Then read `.cpo/templates/planning-brief.md` for the full planning "
        f"pipeline template.\n\n"
        f"## Preset: {preset}\n\n"
        f"Run these phases (budget: ~{budget} minutes):\n"
        f"{phase_list}\n\n"
    )

    if preset == "light":
        prompt += (
            "## Light Preset Instructions\n\n"
            "Skip deep research and prerequisites. Go straight to:\n"
            "1. Read the topic\n"
            "2. Define scope: deliverables, constraints, acceptance criteria\n"
            "3. Split into briefs using the template at "
            "`.cpo/templates/brief-template.md`\n"
            "4. Write each brief to `.planning/{run_id}/output/brief-N.md`\n"
            "5. Write `.planning/{run_id}/result.md` with summary\n"
            "6. Say 'PLANNING COMPLETE'\n\n"
        ).format(run_id=run_id)
    elif preset == "standard":
        prompt += (
            "## Standard Preset Instructions\n\n"
            "Run the full planning pipeline:\n"
            "1. Read the topic\n"
            "2. Phase 0: Prerequisites audit — environment, dependencies, "
            "existing solutions (check `/skill-library search`, search externally)\n"
            "3. Phase 0.5: Human setup gate — list items needing human action\n"
            "4. Phase 0.7: Verification capability check\n"
            "5. Phase 1: Scope definition — deliverables, constraints, "
            "acceptance criteria\n"
            "6. Phase 2: Research — read codebase, check skill library, "
            "search externally\n"
            "7. Phase 3: Architecture decisions with tradeoffs\n"
            "8. Phase 4: Phasing and dependencies\n"
            "9. Phase 5: Split into briefs with verification sections "
            "using `.cpo/templates/brief-template.md`\n"
            "10. Write each brief to `.planning/{run_id}/output/brief-N.md`\n"
            "11. Write `.planning/{run_id}/result.md` with summary\n"
            "12. Say 'PLANNING COMPLETE'\n\n"
        ).format(run_id=run_id)
    else:  # deep
        prompt += (
            "## Deep Preset Instructions\n\n"
            "Run the full pipeline with embedded panel for research:\n"
            "1. Read the topic\n"
            "2. Phase 0-0.7: Full prerequisites audit and verification\n"
            "3. Phase 1: Scope definition\n"
            "4. Phase 2: Research — during this phase, launch a solution "
            "discovery panel for the core research question:\n"
            "   ```\n"
            "   python3 tools/launch.py --role panel --topic \"<research question "
            "derived from topic>\" --preset quick\n"
            "   ```\n"
            "   Wait for panel result at `.panel/<panel-run-id>/result.md`, "
            "then incorporate the perspectives.\n"
            "   If the panel command fails (e.g., panel_runner.py not available), "
            "fall back to direct analysis and note: "
            "'Panel not available, research phase used direct analysis only.'\n"
            "5. Phase 3: Architecture decisions incorporating panel perspectives\n"
            "6. Phase 4: Phasing and dependencies\n"
            "7. Phase 5: Split into briefs with verification sections "
            "using `.cpo/templates/brief-template.md`\n"
            "8. Phase 6: Integration planning — cross-brief verification points\n"
            "9. Phase 7: E2E test planning — final validation scenario\n"
            "10. Write each brief to `.planning/{run_id}/output/brief-N.md`\n"
            "11. Write a project envelope to `.planning/{run_id}/envelope.md` "
            "using `.cpo/templates/project-envelope.md`\n"
            "12. Write `.planning/{run_id}/result.md` with summary\n"
            "13. Say 'PLANNING COMPLETE'\n\n"
        ).format(run_id=run_id)

    prompt += (
        "## Output Requirements\n\n"
        "### result.md must include:\n"
        "- Scope and objectives\n"
        "- Prerequisites (resolved / needs human action)\n"
        "- Brief list with dependencies: Brief 1 → Brief 2 → Brief 3 "
        "(or parallel groups)\n"
        "- Estimated effort per brief (S/M/L/XL)\n"
        "- Recommended dispatch strategy (sequential, parallel, "
        "director-managed)\n\n"
        "### Each brief must:\n"
        "- Follow the template at `.cpo/templates/brief-template.md`\n"
        "- Be ready for dispatch via `launch.py --role pair`\n"
        "- Include a 'Challenge Points' section with 2-3 assumptions to verify\n"
        "- Include verification sections referencing established capabilities\n\n"
        "## Important\n\n"
        "- Bias towards full agent autonomy — batch human dependencies into one gate\n"
        "- Check `.cpo/backlog.json` for related items if it exists\n"
        "- Challenge your own assumptions — state the strongest counterargument "
        "for each major decision\n"
        "- Begin immediately.\n"
    )

    return prompt


def launch_planning(args) -> dict:
    """Launch a planning agent.

    Steps:
    1. Create planning directory: .planning/<run-id>/
    2. Write topic.md and config.json
    3. Fork calling session (if --session-id) → planning tmux session
    4. Build planning prompt from template + topic + preset
    5. Inject prompt into forked session
    """
    topic = args.topic
    preset = args.preset or "standard"
    provider = args.provider
    server = args.tmux_server
    json_mode = args.json
    model = args.model
    session_id = getattr(args, "session_id", None)

    # Validate preset
    if preset not in PLANNING_PRESETS:
        return {"status": "error", "step": "validate",
                "error": f"Invalid planning preset: {preset}. "
                         f"Choose from: light, standard, deep",
                "cleaned_up": False}

    preset_cfg = PLANNING_PRESETS[preset]

    # Resolve model
    if model:
        model_id = MODEL_IDS.get(model, MODEL_IDS["sonnet"])
        model_name = model
    else:
        model_id = preset_cfg["model_id"]
        model_name = preset_cfg["default_model"]

    # Generate run ID
    import hashlib
    ts = time.strftime("%Y%m%d-%H%M%S")
    topic_hash = hashlib.md5(topic.encode()).hexdigest()[:6]
    run_id = f"plan-{ts}-{topic_hash}"

    # Planning directory
    plan_dir = os.path.join(PROJECT_DIR, ".planning", run_id)
    output_dir = os.path.join(plan_dir, "output")

    result = {
        "status": "ok",
        "role": "planning",
        "run_id": run_id,
        "preset": preset,
        "model": model_name,
        "topic": topic,
        "plan_dir": f".planning/{run_id}",
        "output_dir": f".planning/{run_id}/output",
    }

    # Dry run
    if args.dry_run:
        steps = [
            f"1. Create planning directory: .planning/{run_id}/",
            f"2. Write topic.md and config.json",
            f"3. Preset: {preset} — phases: {', '.join(preset_cfg['phases'])}",
            f"4. Budget: ~{preset_cfg['budget_minutes']} min | Model: {model_name}",
        ]
        if session_id:
            steps.append(
                f"5. Fork session {session_id} → planning-{run_id} tmux session"
            )
        else:
            steps.append(
                "5. Create fresh planning session (no fork — no --session-id)"
            )
        steps += [
            f"6. Inject planning prompt into session",
            f"7. Briefs will be at .planning/{run_id}/output/",
        ]
        if preset_cfg["embed_panel"]:
            steps.append(
                "8. Deep preset: agent will launch embedded panel during Phase 2"
            )
        if json_mode:
            result["status"] = "dry_run"
            result["steps"] = steps
            return result
        print("Dry run — would execute:")
        for s in steps:
            print(f"  {s}")
        return {"status": "dry_run"}

    # --- Execute ---
    plan_session = f"planning-{run_id}"[:SESSION_NAME_MAX]
    created_session = False

    try:
        # Step 1: Create planning directory
        log(f"creating planning directory: .planning/{run_id}/", json_mode)
        os.makedirs(output_dir, exist_ok=True)

        # Step 2: Write topic.md
        topic_path = os.path.join(plan_dir, "topic.md")
        with open(topic_path, "w") as f:
            f.write(f"# Planning Topic\n\n{topic}\n")

        # Write config.json
        config = {
            "run_id": run_id,
            "topic": topic,
            "preset": preset,
            "model": model_name,
            "model_id": model_id,
            "phases": preset_cfg["phases"],
            "budget_minutes": preset_cfg["budget_minutes"],
            "embed_panel": preset_cfg["embed_panel"],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        config_path = os.path.join(plan_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

        # Step 3: Create planning session
        log(f"creating planning session: {plan_session}", json_mode)
        if session_id:
            # Fork the calling session
            fork_cmd = (
                f"claude --resume {session_id} --fork-session "
                f"--dangerously-skip-permissions"
            )
            tmux_cmd(
                ["new-session", "-d", "-s", plan_session, "-c", PROJECT_DIR],
                server,
            )
            created_session = True
            time.sleep(1)
            tmux_cmd(
                ["send-keys", "-t", plan_session, fork_cmd, "Enter"],
                server,
            )
        else:
            # Fresh session with model selection
            tmux_cmd(
                ["new-session", "-d", "-s", plan_session, "-c", PROJECT_DIR],
                server,
            )
            created_session = True
            provider_cmd = (
                f"claude --dangerously-skip-permissions --model {model_id}"
            )
            tmux_cmd(
                ["send-keys", "-t", plan_session, provider_cmd, "Enter"],
                server,
            )

        # Step 4: Wait for initialization
        log(f"waiting {INIT_WAIT['claude']}s for session to initialize",
            json_mode)
        step_wait_init("claude")

        # Step 5: Inject planning prompt
        log("injecting planning prompt", json_mode)
        planning_prompt = _build_planning_prompt(run_id, topic, preset, config)
        step_inject_text(plan_session, planning_prompt, server)

        # Step 6: Register agent
        _register_agent(plan_session, "planning", provider, plan_session,
                        server,
                        brief_ref=f".planning/{run_id}/config.json")

        result["session"] = plan_session

        log(f"planning {run_id} launched", json_mode)
        if not json_mode:
            print(f"\n  Planning: {run_id}")
            print(f"  Session: {plan_session}")
            print(f"  Preset: {preset} | Model: {model_name}")
            print(f"  Budget: ~{preset_cfg['budget_minutes']} min")
            print(f"  Briefs will be at: .planning/{run_id}/output/")

        return result

    except Exception as e:
        log(f"error: {e}", json_mode)
        if created_session:
            tmux_cmd(["kill-session", "-t", plan_session], server)
        return {"status": "error", "step": "launch_planning",
                "error": str(e), "cleaned_up": True}


# ---------------------------------------------------------------------------
# Role: panel
# ---------------------------------------------------------------------------

PANEL_RUNNER = os.path.join(SCRIPT_DIR, "panel_runner.py")

PANEL_ORCH_CRON_PROMPT = (
    "Panel orchestrator 5-min check. Check round progress: "
    "python3 tools/panel_runner.py status --run-id <your-run-id>. "
    "If a persona stalled, note it and proceed with available outputs. "
    "If all rounds complete, write result.md and clean up."
)


def launch_panel(args) -> dict:
    """Launch a solution discovery panel.

    Steps:
    1. Initialize panel via panel_runner.py (creates dir, config, selects personas)
    2. Fork calling session (if --session-id provided) → orchestrator tmux session
    3. Spawn parallel persona tmux sessions with Claude + persona system prompts
    4. Inject orchestrator brief into forked session
    5. Print panel info and return
    """
    topic = args.topic
    preset = args.preset or "standard"
    provider = args.provider
    server = args.tmux_server
    json_mode = args.json
    model = args.model  # May be None — panel_runner uses preset default
    session_id = getattr(args, "session_id", None)
    personas_arg = getattr(args, "personas", None)
    rounds_arg = getattr(args, "rounds", None)

    # Generate run ID
    import hashlib
    ts = time.strftime("%Y%m%d-%H%M%S")
    topic_hash = hashlib.md5(topic.encode()).hexdigest()[:6]
    run_id = f"panel-{ts}-{topic_hash}"

    # Build init command
    init_cmd = [
        sys.executable, PANEL_RUNNER, "init",
        "--run-id", run_id,
        "--topic", topic,
        "--preset", preset,
    ]
    if personas_arg:
        init_cmd += ["--personas", personas_arg]
    if rounds_arg:
        init_cmd += ["--rounds", str(rounds_arg)]
    if model:
        init_cmd += ["--model", model]
    init_cmd.append("--json")

    result = {
        "status": "ok",
        "role": "panel",
        "run_id": run_id,
        "preset": preset,
        "topic": topic,
    }

    # Dry run
    if args.dry_run:
        steps = [
            f"1. Initialize panel: {run_id} (preset={preset})",
            f"2. Topic: {topic[:80]}{'...' if len(topic) > 80 else ''}",
        ]
        if session_id:
            steps.append(f"3. Fork session {session_id} → panel-orchestrator-{run_id}")
        else:
            steps.append("3. Create fresh orchestrator session (no fork — no --session-id)")
        steps += [
            f"4. Spawn persona sessions with Claude (model: {model or 'preset default'})",
            f"5. Inject orchestrator brief into forked session",
            f"6. Set up 5m cron on orchestrator for progress checking",
            f"7. Panel runs autonomously; result at .panel/{run_id}/result.md",
        ]
        if json_mode:
            result["status"] = "dry_run"
            result["steps"] = steps
            return result
        print("Dry run — would execute:")
        for s in steps:
            print(f"  {s}")
        return {"status": "dry_run"}

    # --- Execute ---
    orch_session = f"po-{hashlib.sha256(run_id.encode()).hexdigest()[:6]}"
    created_sessions = []

    try:
        # Step 1: Initialize panel
        log("initializing panel", json_mode)
        r = subprocess.run(init_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return {"status": "error", "step": "init",
                    "error": f"panel_runner init failed: {r.stderr.strip()}",
                    "cleaned_up": False}

        config = json.loads(r.stdout)
        personas = config["personas"]
        rounds = config["rounds"]
        panel_model = config.get("model", "sonnet")
        model_id = config.get("model_id", "claude-sonnet-4-6")
        result["personas"] = personas
        result["rounds"] = rounds
        result["model"] = panel_model

        # Step 2: Create orchestrator session
        log(f"creating orchestrator session: {orch_session}", json_mode)
        if session_id:
            # Fork the calling session
            fork_cmd = (
                f"claude --resume {session_id} --fork-session "
                f"--dangerously-skip-permissions"
            )
            tmux_cmd(["new-session", "-d", "-s", orch_session, "-c", PROJECT_DIR], server)
            created_sessions.append(orch_session)
            time.sleep(1)
            tmux_cmd(["send-keys", "-t", orch_session, fork_cmd, "Enter"], server)
        else:
            # Fresh orchestrator session
            tmux_cmd(["new-session", "-d", "-s", orch_session, "-c", PROJECT_DIR], server)
            created_sessions.append(orch_session)
            provider_cmd = PROVIDER_COMMANDS.get(provider, PROVIDER_COMMANDS["claude"])
            tmux_cmd(["send-keys", "-t", orch_session, provider_cmd, "Enter"], server)

        # Step 3: Spawn persona sessions
        log(f"spawning {len(personas)} persona sessions", json_mode)
        for persona in personas:
            sess_name = config["tmux_sessions"][persona]
            # Truncate session name
            sess_name = sess_name[:SESSION_NAME_MAX]

            tmux_cmd(["new-session", "-d", "-s", sess_name, "-c", PROJECT_DIR], server)
            created_sessions.append(sess_name)
            time.sleep(0.5)

            # Launch Claude with model selection
            claude_cmd = f"claude --dangerously-skip-permissions --model {model_id}"
            tmux_cmd(["send-keys", "-t", sess_name, claude_cmd, "Enter"], server)

        # Step 4: Wait for initialization
        log(f"waiting {INIT_WAIT['claude']}s for sessions to initialize", json_mode)
        step_wait_init("claude")

        # Step 5: Inject orchestrator brief
        log("injecting orchestrator brief", json_mode)
        orch_brief = _build_orchestrator_brief(run_id, config)
        step_inject_text(orch_session, orch_brief, server)

        # Step 6: Set up 5-min cron on orchestrator
        log("setting up 5m cron on orchestrator", json_mode)
        panel_cron_prompt = PANEL_ORCH_CRON_PROMPT.replace(
            "<your-run-id>", run_id)
        step_setup_cron(orch_session, provider, "5m", panel_cron_prompt,
                        server, f"panel-orch-{run_id}", json_mode)

        # Step 7: Register agents
        _register_agent(orch_session, "orchestrator", provider, orch_session, server,
                        brief_ref=f".panel/{run_id}/config.json")
        for persona in personas:
            sess_name = config["tmux_sessions"][persona][:SESSION_NAME_MAX]
            _register_agent(sess_name, "panelist", provider, sess_name, server,
                            brief_ref=f".panel/{run_id}/config.json")

        result["orchestrator"] = orch_session
        result["persona_sessions"] = {
            p: config["tmux_sessions"][p][:SESSION_NAME_MAX] for p in personas
        }

        log(f"panel {run_id} launched", json_mode)
        if not json_mode:
            print(f"\n  Panel: {run_id}")
            print(f"  Orchestrator: {orch_session}")
            print(f"  Personas: {', '.join(personas)}")
            print(f"  Rounds: {rounds} | Model: {panel_model}")
            print(f"  Results will be at: .panel/{run_id}/result.md")

        return result

    except Exception as e:
        log(f"error: {e}", json_mode)
        # Cleanup created sessions
        for sess in created_sessions:
            tmux_cmd(["kill-session", "-t", sess], server)
        return {"status": "error", "step": "launch_panel",
                "error": str(e), "cleaned_up": True}


def _build_orchestrator_brief(run_id: str, config: dict) -> str:
    """Build the orchestrator instruction prompt."""
    personas = config["personas"]
    rounds = config["rounds"]
    timeout = config.get("timeout_minutes", 30)
    poll_interval = max(1, timeout // 15)  # Poll roughly 15 times per timeout

    return (
        f"You are the Panel Orchestrator for run '{run_id}'. "
        f"Your job is to manage {rounds} round(s) of a solution discovery panel "
        f"with {len(personas)} personas: {', '.join(personas)}.\n\n"
        f"## Your Workflow\n\n"
        f"For each round:\n"
        f"1. Start the round: `python3 tools/panel_runner.py start-round --run-id {run_id} --round <N>`\n"
        f"2. Poll for completion every {poll_interval} minutes: "
        f"`python3 tools/panel_runner.py check-round --run-id {run_id} --round <N>`\n"
        f"3. When complete, collect outputs: "
        f"`python3 tools/panel_runner.py collect --run-id {run_id} --round <N>`\n"
        f"4. Read the collected perspectives and write your synthesis to "
        f"`.panel/{run_id}/synthesis/round-<N>-synthesis.md`\n"
        f"5. If more rounds remain, start the next round with: "
        f"`python3 tools/panel_runner.py start-round --run-id {run_id} --round <N+1> "
        f"--synthesis .panel/{run_id}/synthesis/round-<N>-synthesis.md`\n\n"
        f"## After Final Round\n\n"
        f"1. Write the final recommendation to `.panel/{run_id}/result.md`\n"
        f"   Include: executive summary, key themes, consensus areas, dissenting views, "
        f"recommended approach, and implementation priorities.\n"
        f"2. Clean up persona sessions: "
        f"`python3 tools/panel_runner.py cleanup --run-id {run_id}`\n"
        f"3. Announce: 'Panel complete. Result at .panel/{run_id}/result.md'\n\n"
        f"## Important Notes\n\n"
        f"- Timeout: {timeout} minutes total. If a persona stalls, note it and proceed with available outputs.\n"
        f"- Start with Round 1 now. The persona sessions are already running and waiting for prompts.\n"
        f"- Your synthesis should be substantive — identify themes, tensions, and non-obvious combinations.\n"
        f"- Begin immediately."
    )


# ---------------------------------------------------------------------------
# Role: advisor
# ---------------------------------------------------------------------------

ADVISOR_CRON_PROMPT = (
    "Advisor 5-min self-check. Answer these questions: "
    "(1) Am I stuck on the same sub-task for 15+ min? If yes, switch approaches. "
    "(2) Is my current exploration still aligned with my chosen focus area? "
    "(3) Should I switch from bottleneck analysis to gap analysis or vice versa? "
    "(4) Have I produced any output this cycle? If 60+ min with nothing, produce something smaller. "
    "(5) Has strategic-direction.md been updated since I last read it? If yes, re-read it. "
    "(6) Have I used a panel in the last 3 cycles? If no and I'm starting a new exploration, launch a panel instead of direct analysis. "
    "(7) Am I waiting for CPO/CEO input? If yes, STOP WAITING and continue with the next exploration cycle."
)


def launch_advisor(args) -> dict:
    """Launch a Strategic Advisor session.

    The advisor is a persistent exploration agent that runs alongside the CPO.
    It explores, researches, and proposes backlog items — it does NOT dispatch
    agents or manage execution.

    Steps:
    1. Create advisor tmux session
    2. Launch provider (default: sonnet model for cost-effective exploration)
    3. Inject advisor instructions + strategic direction
    4. Set up 5-min progress cron
    5. Register in agent registry
    """
    provider = args.provider
    server = args.tmux_server
    json_mode = args.json
    direction = os.path.abspath(args.direction) if args.direction else None
    model = args.model or "sonnet"
    session_id = getattr(args, "session_id", None)

    advisor_session = "advisor"
    workdir = PROJECT_DIR

    result = {
        "status": "ok",
        "role": "advisor",
        "session": advisor_session,
        "provider": provider,
        "model": model,
    }

    # Validate
    if direction and not os.path.isfile(direction):
        return {"status": "error", "step": "validate",
                "error": f"Strategic direction file not found: {direction}",
                "cleaned_up": False}

    # Dry run
    if args.dry_run:
        steps = [
            f"1. Create tmux session: {advisor_session}"
            + (f" (server: {server})" if server else ""),
            f"2. Launch {provider} in {advisor_session}"
            + (f" (model: {model})" if model else ""),
            f"3. Wait {INIT_WAIT[provider]}s for initialization",
        ]
        if session_id:
            steps[0] = (
                f"1. Fork session {session_id} → {advisor_session}"
                + (f" (server: {server})" if server else "")
            )
        if direction:
            steps.append(f"4. Inject advisor instructions + strategic direction ({direction})")
        else:
            steps.append("4. Inject advisor instructions (no strategic direction file)")
        steps += [
            "5. Set up 5-min progress cron",
            "6. Register in agent registry",
            "7. Verify session active",
        ]
        if json_mode:
            result["status"] = "dry_run"
            result["steps"] = steps
            return result
        print("Dry run — would execute:")
        for s in steps:
            print(f"  {s}")
        return {"status": "dry_run"}

    # Execute
    created_session = False
    try:
        # Create or fork session
        if session_id:
            log(f"forking session {session_id} → {advisor_session}", json_mode)
            # Use claude session fork if available
            fork_result = subprocess.run(
                ["claude", "session", "fork", session_id,
                 "--name", advisor_session],
                capture_output=True, text=True, cwd=workdir,
            )
            if fork_result.returncode != 0:
                log("fork failed, creating fresh session instead", json_mode)
                step_create_sessions([advisor_session], workdir, server)
            created_session = True
        else:
            log(f"creating tmux session {advisor_session}", json_mode)
            step_create_sessions([advisor_session], workdir, server)
            created_session = True

        # Launch provider
        log(f"launching {provider} in {advisor_session}", json_mode)
        provider_cmd = PROVIDER_COMMANDS[provider]
        if provider == "claude" and model:
            provider_cmd += f" --model {model}"
        tmux_cmd(["send-keys", "-t", advisor_session, provider_cmd, "Enter"],
                 server)
        time.sleep(2)
        tmux_cmd(["send-keys", "-t", advisor_session, "Enter"], server)

        log(f"waiting {INIT_WAIT[provider]}s for initialization", json_mode)
        step_wait_init(provider)

        # Inject advisor instructions
        log("injecting advisor instructions", json_mode)
        direction_ref = ""
        if direction:
            direction_rel = os.path.relpath(direction, PROJECT_DIR)
            direction_ref = (
                f" Then read {direction_rel} for the current strategic "
                f"direction — this is your north star for exploration."
            )
        advisor_prompt = (
            "Read .cpo/advisor/advisor-instructions.md for your complete "
            "operating procedures. You are the Strategic Advisor — you explore, "
            "research, and propose backlog items. You do NOT dispatch agents or "
            "manage execution."
            + direction_ref +
            " Read .cpo/advisor/bottleneck-analysis.md and "
            ".cpo/advisor/gap-analysis.md for current state, then begin "
            "your first exploration cycle."
        )
        step_inject_text(advisor_session, advisor_prompt, server)

        # Set up 5-min cron
        log("setting up 5-min progress cron", json_mode)
        step_setup_cron(advisor_session, provider, "5m", ADVISOR_CRON_PROMPT,
                        server, "advisor-main", json_mode)

        # Verify
        log("verifying advisor is active", json_mode)
        active = step_verify(advisor_session, server)
        if not active:
            log("warning: advisor may not have started processing yet",
                json_mode)
            result["warning"] = "advisor activity not confirmed"

        # Register
        direction_rel = os.path.relpath(direction, PROJECT_DIR) if direction else None
        _register_agent(advisor_session, "advisor", provider, advisor_session,
                        server, brief_ref=direction_rel)

        log("advisor launch complete", json_mode)
        return result

    except Exception as e:
        log(f"error: {e}", json_mode)
        cleanup(
            [advisor_session if created_session else None],
            server, None, json_mode,
        )
        return {"status": "error", "step": "launch_advisor",
                "error": str(e), "cleaned_up": True}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Unified agent launcher — pairs, directors, CPOs, queues, panels, planning, and advisors.",
    )
    parser.add_argument(
        "--role", default="pair",
        choices=["pair", "director", "cpo", "queue", "panel", "planning", "advisor", "observer"],
        help="Launch role (default: pair)",
    )
    parser.add_argument(
        "--brief", default=None,
        help="Path to the brief file (required for --role pair)",
    )
    parser.add_argument(
        "--branch", default=None,
        help="Git branch name for the worktree (required for --role pair)",
    )
    parser.add_argument(
        "--handover", default=None,
        help="Path to handover file (optional for --role director)",
    )
    parser.add_argument(
        "--provider", default="claude", choices=["claude", "codex"],
        help="Provider to use (default: claude)",
    )
    parser.add_argument(
        "--tmux-server", default=None,
        help="tmux -L server name for session isolation",
    )
    parser.add_argument(
        "--supervisor-cron", default=None,
        help="If set, include cron setup instruction (e.g. '4m')",
    )
    parser.add_argument(
        "--verification-level", default=None, type=int, choices=[2, 3, 4],
        help="Required verification level for this pair (2=runs, 3=flow works, 4=edge cases). Injected into supervisor prompt + cron.",
    )
    parser.add_argument(
        "--worktree-path", default=None,
        help="Override worktree location (default: /tmp/<branch-name>)",
    )
    parser.add_argument(
        "--skip-comms", action="store_true",
        help="Skip Telegram/comms setup (--role cpo only)",
    )
    # Queue-specific arguments
    parser.add_argument(
        "--queue-config", default=None,
        help="Path to queue.json (required for --role queue)",
    )
    parser.add_argument(
        "--items-file", default=None,
        help="Batch file with URLs to load into queue (--role queue)",
    )
    parser.add_argument(
        "--learning-mode", default=None,
        choices=["none", "short", "medium", "intense"],
        help="Override learning mode from queue.json (--role queue)",
    )
    parser.add_argument(
        "--daemon-mode", default=None,
        choices=["active", "passive", "off"],
        help="Daemon mode: active/passive/off (default: passive, --role queue)",
    )
    parser.add_argument(
        "--skip-director", action="store_true",
        help="Start daemon only, no director (--role queue)",
    )
    # Panel-specific arguments
    parser.add_argument(
        "--topic", default=None,
        help="Panel topic/question (required for --role panel)",
    )
    parser.add_argument(
        "--preset", default=None,
        choices=["quick", "light", "standard", "deep"],
        help="Preset: panel (quick/standard/deep), planning (light/standard/deep)",
    )
    parser.add_argument(
        "--personas", default=None,
        help="Comma-separated persona names for panel (overrides preset count)",
    )
    parser.add_argument(
        "--rounds", default=None, type=int,
        help="Number of panel rounds (overrides preset)",
    )
    parser.add_argument(
        "--model", default=None, choices=["opus", "sonnet", "haiku"],
        help="Claude model for panel sessions (default: preset-dependent)",
    )
    parser.add_argument(
        "--session-id", default=None,
        help="Caller's Claude session ID for forking (--role panel/planning/advisor)",
    )
    # Advisor-specific arguments
    parser.add_argument(
        "--direction", default=None,
        help="Path to strategic direction file (--role advisor)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON instead of human-readable text",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without executing",
    )
    # Observer arguments
    parser.add_argument(
        "--observe", action="store_true",
        help="Spawn a passive observer session alongside this role",
    )
    parser.add_argument(
        "--observer-focus", type=str, default=None,
        help="Custom focus for the observer (overrides default)",
    )
    parser.add_argument(
        "--target", type=str, default=None,
        help="Target session name for --role observer",
    )
    parser.add_argument(
        "--run-id", type=str, default=None,
        help="Explicit run-id for observer (default: auto-generated)",
    )
    parser.add_argument(
        "--report-path", type=str, default=None,
        help="Override observer report path",
    )

    args = parser.parse_args()

    # Validate role-specific requirements
    if args.role == "pair":
        if not args.brief:
            parser.error("--brief is required for --role pair")
        if not args.branch:
            parser.error("--branch is required for --role pair")
    elif args.role == "queue":
        if not args.queue_config:
            parser.error("--queue-config is required for --role queue")
    elif args.role == "panel":
        if not args.topic:
            parser.error("--topic is required for --role panel")
    elif args.role == "planning":
        if not args.topic:
            parser.error("--topic is required for --role planning")
    elif args.role == "observer":
        if not args.target:
            parser.error("--target is required for --role observer")

    # Dispatch to role handler
    handlers = {
        "pair": launch_pair,
        "director": launch_director,
        "cpo": launch_cpo,
        "queue": launch_queue,
        "panel": launch_panel,
        "planning": launch_planning,
        "advisor": launch_advisor,
        "observer": launch_observer,
    }
    result = handlers[args.role](args)

    if args.json or result.get("status") == "error":
        print(json.dumps(result, indent=2))

    sys.exit(0 if result["status"] in ("ok", "dry_run") else 1)


if __name__ == "__main__":
    main()
