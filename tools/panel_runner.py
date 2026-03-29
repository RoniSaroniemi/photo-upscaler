#!/usr/bin/env python3
"""Panel runner — deterministic orchestration tool for solution discovery panels.

Handles the mechanical parts of panel coordination so the orchestrator agent
can focus on synthesis and judgment.

Commands:
    init         Create panel directory structure and config
    start-round  Inject prompts into all persona sessions for a round
    check-round  Check if all persona output files exist for a round
    collect      Concatenate all round outputs into a single document
    status       Show overall panel status
    cleanup      Kill all persona tmux sessions

Stdlib-only. No pip dependencies.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
PANEL_DIR = os.path.join(PROJECT_DIR, ".panel")
PERSONA_DIR = os.path.join(PROJECT_DIR, ".cpo", "templates", "persona-prompts")
OUTPUT_FORMAT = os.path.join(PROJECT_DIR, ".cpo", "templates", "panel-output-format.md")

# All available personas (filename stems)
ALL_PERSONAS = [
    "moonshot-thinker",
    "speed-builder",
    "compounding-strategist",
    "risk-analyst",
    "user-advocate",
    "technical-architect",
    "business-analyst",
]

# Short abbreviations for persona names (keep session names under 30 chars)
PERSONA_SHORT = {
    "moonshot-thinker": "moonshot",
    "speed-builder": "speed",
    "compounding-strategist": "compound",
    "risk-analyst": "risk",
    "user-advocate": "user",
    "technical-architect": "tecarch",
    "business-analyst": "bizanly",
}

# Topic keyword → recommended personas mapping
TOPIC_PERSONAS = {
    "technical": ["moonshot-thinker", "speed-builder", "technical-architect", "risk-analyst"],
    "architecture": ["moonshot-thinker", "speed-builder", "technical-architect", "risk-analyst"],
    "infrastructure": ["compounding-strategist", "technical-architect", "speed-builder", "risk-analyst"],
    "platform": ["compounding-strategist", "technical-architect", "speed-builder", "risk-analyst"],
    "product": ["moonshot-thinker", "user-advocate", "business-analyst", "compounding-strategist"],
    "user": ["moonshot-thinker", "user-advocate", "business-analyst", "compounding-strategist"],
    "market": ["speed-builder", "business-analyst", "user-advocate", "risk-analyst"],
    "business": ["speed-builder", "business-analyst", "user-advocate", "risk-analyst"],
    "go-to-market": ["speed-builder", "business-analyst", "user-advocate", "risk-analyst"],
    "creative": ["moonshot-thinker", "compounding-strategist", "user-advocate", "speed-builder"],
    "vision": ["moonshot-thinker", "compounding-strategist", "user-advocate", "speed-builder"],
    "risk": ["risk-analyst", "business-analyst", "technical-architect", "compounding-strategist"],
    "decision": ["risk-analyst", "business-analyst", "technical-architect", "compounding-strategist"],
    "security": ["risk-analyst", "technical-architect", "speed-builder", "compounding-strategist"],
    "scale": ["technical-architect", "compounding-strategist", "risk-analyst", "moonshot-thinker"],
    "api": ["technical-architect", "speed-builder", "risk-analyst", "user-advocate"],
    "database": ["technical-architect", "speed-builder", "risk-analyst", "compounding-strategist"],
}

# Preset configurations
PRESETS = {
    "quick": {"persona_count": 3, "rounds": 1, "timeout_minutes": 15, "default_model": "haiku"},
    "standard": {"persona_count": 5, "rounds": 2, "timeout_minutes": 30, "default_model": "sonnet"},
    "deep": {"persona_count": 7, "rounds": 3, "timeout_minutes": 60, "default_model": "opus"},
}

MODEL_MAP = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_dir(run_id: str) -> str:
    return os.path.join(PANEL_DIR, run_id)


def _load_config(run_id: str) -> dict:
    config_path = os.path.join(_run_dir(run_id), "config.json")
    with open(config_path) as f:
        return json.load(f)


def _save_config(run_id: str, config: dict) -> None:
    config_path = os.path.join(_run_dir(run_id), "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def _tmux_cmd(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux"] + args, capture_output=True, text=True)


def _tmux_session_exists(session: str) -> bool:
    r = _tmux_cmd(["has-session", "-t", session])
    return r.returncode == 0


def _read_persona_prompt(persona: str) -> str:
    path = os.path.join(PERSONA_DIR, f"{persona}.md")
    with open(path) as f:
        return f.read()


def _read_output_format() -> str:
    with open(OUTPUT_FORMAT) as f:
        return f.read()


def select_personas(topic: str, count: int) -> list:
    """Auto-select personas based on topic keywords."""
    topic_lower = topic.lower()
    scores = {p: 0 for p in ALL_PERSONAS}

    for keyword, personas in TOPIC_PERSONAS.items():
        if keyword in topic_lower:
            for i, p in enumerate(personas):
                scores[p] += len(personas) - i  # Higher score for earlier position

    ranked = sorted(ALL_PERSONAS, key=lambda p: scores[p], reverse=True)

    # If no keywords matched, use a balanced default set
    if all(v == 0 for v in scores.values()):
        default_order = [
            "technical-architect", "risk-analyst", "speed-builder",
            "moonshot-thinker", "user-advocate", "compounding-strategist",
            "business-analyst",
        ]
        return default_order[:count]

    return ranked[:count]


# ---------------------------------------------------------------------------
# Command: init
# ---------------------------------------------------------------------------

def cmd_init(args) -> int:
    """Create panel directory structure and config."""
    run_id = args.run_id
    topic = args.topic
    preset_name = args.preset or "standard"
    preset = PRESETS[preset_name]

    # Parse personas
    if args.personas:
        personas = [p.strip() for p in args.personas.split(",")]
        for p in personas:
            if p not in ALL_PERSONAS:
                print(f"Unknown persona: {p}", file=sys.stderr)
                print(f"Available: {', '.join(ALL_PERSONAS)}", file=sys.stderr)
                return 1
    else:
        count = args.persona_count or preset["persona_count"]
        personas = select_personas(topic, count)

    rounds = args.rounds or preset["rounds"]
    model = args.model or preset["default_model"]

    run_path = _run_dir(run_id)
    os.makedirs(run_path, exist_ok=True)

    # Create round directories
    for r in range(1, rounds + 1):
        os.makedirs(os.path.join(run_path, f"round-{r}"), exist_ok=True)
    os.makedirs(os.path.join(run_path, "synthesis"), exist_ok=True)

    # Write topic
    with open(os.path.join(run_path, "topic.md"), "w") as f:
        f.write(f"# Panel Topic\n\n{topic}\n")

    # Write config
    config = {
        "run_id": run_id,
        "topic": topic,
        "preset": preset_name,
        "personas": personas,
        "rounds": rounds,
        "model": model,
        "model_id": MODEL_MAP.get(model, model),
        "timeout_minutes": preset["timeout_minutes"],
        "created_at": _utcnow(),
        "status": "initialized",
        "current_round": 0,
        "tmux_sessions": {
            p: f"p-{hashlib.sha256(run_id.encode()).hexdigest()[:6]}-{PERSONA_SHORT.get(p, p[:7])}"
            for p in personas
        },
    }
    _save_config(run_id, config)

    if args.json:
        print(json.dumps(config, indent=2))
    else:
        print(f"Panel initialized: {run_path}")
        print(f"  Preset: {preset_name}")
        print(f"  Personas: {', '.join(personas)}")
        print(f"  Rounds: {rounds}")
        print(f"  Model: {model} ({MODEL_MAP.get(model, model)})")
        print(f"  Timeout: {preset['timeout_minutes']}m")
    return 0


# ---------------------------------------------------------------------------
# Command: start-round
# ---------------------------------------------------------------------------

def cmd_start_round(args) -> int:
    """Inject prompts into all persona sessions for a round."""
    run_id = args.run_id
    round_num = args.round
    config = _load_config(run_id)
    personas = config["personas"]
    topic = config["topic"]
    run_path = _run_dir(run_id)
    synthesis_path = args.synthesis

    # Read output format template
    output_format = _read_output_format()

    round_dir = os.path.join(run_path, f"round-{round_num}")
    os.makedirs(round_dir, exist_ok=True)

    injected = []
    failed = []

    for persona in personas:
        session = config["tmux_sessions"][persona]

        # Check session exists
        if not _tmux_session_exists(session):
            failed.append(f"{persona} (session {session} not found)")
            continue

        # Build prompt
        if round_num == 1:
            prompt = _build_round1_prompt(persona, topic, output_format, run_path)
        else:
            prompt = _build_round2_prompt(
                persona, topic, output_format, run_path, round_num, synthesis_path
            )

        # Inject via tmux send-keys using bracketed paste for safety
        _inject_prompt(session, prompt)
        injected.append(persona)

    # Update config
    config["current_round"] = round_num
    config["status"] = f"round-{round_num}-running"
    _save_config(run_id, config)

    if args.json:
        print(json.dumps({"round": round_num, "injected": injected, "failed": failed}))
    else:
        print(f"Round {round_num} started.")
        if injected:
            print(f"  Injected: {', '.join(injected)}")
        if failed:
            print(f"  Failed: {', '.join(failed)}")
        print(f"  Waiting for: {', '.join(injected)}")

    return 1 if failed and not injected else 0


def _build_round1_prompt(persona: str, topic: str, output_format: str, run_path: str) -> str:
    persona_prompt = _read_persona_prompt(persona)
    output_path = os.path.join(run_path, f"round-1/{persona}.md")
    # Make path relative to project dir for the agent
    rel_output = os.path.relpath(output_path, PROJECT_DIR)

    return (
        f"You are participating in a Solution Discovery Panel.\n\n"
        f"## Your Persona\n\n{persona_prompt}\n\n"
        f"## The Challenge\n\n{topic}\n\n"
        f"## Output Format\n\n{output_format}\n\n"
        f"## Instructions\n\n"
        f"Write your Round 1 perspective following the output format above. "
        f"Be concrete and specific — name technologies, patterns, and trade-offs.\n\n"
        f"Write your output to: `{rel_output}`\n\n"
        f"Use the Write tool to create the file. Do not output anything else after writing the file."
    )


def _build_round2_prompt(persona: str, topic: str, output_format: str,
                         run_path: str, round_num: int, synthesis_path: str = None) -> str:
    persona_prompt = _read_persona_prompt(persona)
    output_path = os.path.join(run_path, f"round-{round_num}/{persona}.md")
    rel_output = os.path.relpath(output_path, PROJECT_DIR)

    # Read previous round outputs for cross-commentary
    prev_round_dir = os.path.join(run_path, f"round-{round_num - 1}")
    perspectives_note = ""
    if os.path.isdir(prev_round_dir):
        files = sorted(f for f in os.listdir(prev_round_dir) if f.endswith(".md"))
        if files:
            rel_dir = os.path.relpath(prev_round_dir, PROJECT_DIR)
            perspectives_note = (
                f"## Other Panelists' Round {round_num - 1} Perspectives\n\n"
                f"Read all .md files in `{rel_dir}/` to see other panelists' perspectives "
                f"before writing your reactions.\n\n"
            )

    synthesis_note = ""
    if synthesis_path and os.path.isfile(synthesis_path):
        rel_synth = os.path.relpath(synthesis_path, PROJECT_DIR)
        synthesis_note = (
            f"## Synthesis from Previous Round\n\n"
            f"Read `{rel_synth}` for the orchestrator's synthesis of the previous round.\n\n"
        )

    return (
        f"You are participating in Round {round_num} of a Solution Discovery Panel.\n\n"
        f"## Your Persona\n\n{persona_prompt}\n\n"
        f"## The Challenge\n\n{topic}\n\n"
        f"{perspectives_note}"
        f"{synthesis_note}"
        f"## Output Format (Round 2 Reactions)\n\n{output_format}\n\n"
        f"## Instructions\n\n"
        f"First, read all other panelists' perspectives from the previous round. "
        f"Then write your Round {round_num} reactions following the Round 2 format above.\n\n"
        f"Write your output to: `{rel_output}`\n\n"
        f"Use the Write tool to create the file. Do not output anything else after writing the file."
    )


def _inject_prompt(session: str, prompt: str) -> None:
    """Inject a prompt into a tmux session using bracketed paste mode."""
    # Use bracketed paste to safely inject multi-line text
    # \x1b[200~ starts bracketed paste, \x1b[201~ ends it
    escaped = prompt.replace("\\", "\\\\").replace("'", "'\\''")

    # Write prompt to a temp file, then use load-buffer + paste-buffer
    # This is more reliable than send-keys for long multi-line text
    import tempfile
    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="panel-prompt-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(prompt)
        # Load into tmux buffer and paste
        _tmux_cmd(["load-buffer", tmp_path])
        _tmux_cmd(["paste-buffer", "-t", session])
        time.sleep(0.5)
        _tmux_cmd(["send-keys", "-t", session, "Enter"])
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Command: check-round
# ---------------------------------------------------------------------------

def cmd_check_round(args) -> int:
    """Check if all persona output files exist for a round."""
    run_id = args.run_id
    round_num = args.round
    config = _load_config(run_id)
    personas = config["personas"]
    run_path = _run_dir(run_id)
    round_dir = os.path.join(run_path, f"round-{round_num}")

    done = []
    pending = []

    for persona in personas:
        path = os.path.join(round_dir, f"{persona}.md")
        if os.path.isfile(path) and os.path.getsize(path) > 50:
            done.append(persona)
        else:
            pending.append(persona)

    all_done = len(pending) == 0

    if args.json:
        print(json.dumps({
            "round": round_num,
            "total": len(personas),
            "done": len(done),
            "pending": len(pending),
            "done_personas": done,
            "pending_personas": pending,
            "complete": all_done,
        }))
    else:
        status = f"{len(done)}/{len(personas)} complete"
        details = []
        for p in personas:
            mark = "\u2713" if p in done else "\u2717"
            details.append(f"{p} {mark}")
        print(f"Round {round_num}: {status}")
        print(f"  {', '.join(details)}")

    # Exit 0 if all done, 1 if still waiting
    return 0 if all_done else 1


# ---------------------------------------------------------------------------
# Command: collect
# ---------------------------------------------------------------------------

def cmd_collect(args) -> int:
    """Concatenate all round outputs into a single document."""
    run_id = args.run_id
    round_num = args.round
    config = _load_config(run_id)
    personas = config["personas"]
    run_path = _run_dir(run_id)
    round_dir = os.path.join(run_path, f"round-{round_num}")
    synthesis_dir = os.path.join(run_path, "synthesis")
    os.makedirs(synthesis_dir, exist_ok=True)

    output_path = os.path.join(synthesis_dir, f"all-round-{round_num}.md")

    parts = []
    parts.append(f"# Panel Round {round_num} — All Perspectives\n")
    parts.append(f"**Topic:** {config['topic']}\n")
    parts.append(f"**Collected at:** {_utcnow()}\n")
    parts.append("---\n")

    collected = 0
    for persona in personas:
        path = os.path.join(round_dir, f"{persona}.md")
        if os.path.isfile(path):
            with open(path) as f:
                content = f.read()
            parts.append(f"\n## === {persona.replace('-', ' ').title()} ===\n")
            parts.append(content)
            parts.append("\n---\n")
            collected += 1
        else:
            parts.append(f"\n## === {persona.replace('-', ' ').title()} ===\n")
            parts.append("*(No output received)*\n")
            parts.append("\n---\n")

    with open(output_path, "w") as f:
        f.write("\n".join(parts))

    rel_path = os.path.relpath(output_path, PROJECT_DIR)
    if args.json:
        print(json.dumps({"path": rel_path, "collected": collected, "total": len(personas)}))
    else:
        print(f"Collected {collected}/{len(personas)} perspectives → {rel_path}")
    return 0


# ---------------------------------------------------------------------------
# Command: status
# ---------------------------------------------------------------------------

def cmd_status(args) -> int:
    """Show overall panel status."""
    run_id = args.run_id
    config = _load_config(run_id)
    run_path = _run_dir(run_id)

    # Check session liveness
    sessions_alive = {}
    for persona, session in config.get("tmux_sessions", {}).items():
        sessions_alive[persona] = _tmux_session_exists(session)

    # Check round completion
    rounds_status = {}
    for r in range(1, config["rounds"] + 1):
        round_dir = os.path.join(run_path, f"round-{r}")
        if not os.path.isdir(round_dir):
            rounds_status[f"round-{r}"] = "not started"
            continue
        done = sum(
            1 for p in config["personas"]
            if os.path.isfile(os.path.join(round_dir, f"{p}.md"))
            and os.path.getsize(os.path.join(round_dir, f"{p}.md")) > 50
        )
        total = len(config["personas"])
        if done == total:
            rounds_status[f"round-{r}"] = "complete"
        elif done > 0:
            rounds_status[f"round-{r}"] = f"in-progress ({done}/{total})"
        else:
            rounds_status[f"round-{r}"] = "not started"

    # Check for final result
    has_result = os.path.isfile(os.path.join(run_path, "result.md"))

    status_obj = {
        "run_id": run_id,
        "status": config.get("status", "unknown"),
        "preset": config.get("preset"),
        "model": config.get("model"),
        "personas": config["personas"],
        "rounds_configured": config["rounds"],
        "rounds_status": rounds_status,
        "sessions_alive": sessions_alive,
        "has_result": has_result,
        "created_at": config.get("created_at"),
    }

    if args.json:
        print(json.dumps(status_obj, indent=2))
    else:
        print(f"Panel: {run_id}")
        print(f"  Status: {config.get('status', 'unknown')}")
        print(f"  Preset: {config.get('preset')} | Model: {config.get('model')}")
        print(f"  Personas: {', '.join(config['personas'])}")
        for rnd, st in rounds_status.items():
            print(f"  {rnd}: {st}")
        alive_count = sum(1 for v in sessions_alive.values() if v)
        print(f"  Sessions alive: {alive_count}/{len(sessions_alive)}")
        if has_result:
            print(f"  Result: .panel/{run_id}/result.md")
    return 0


# ---------------------------------------------------------------------------
# Command: cleanup
# ---------------------------------------------------------------------------

def cmd_cleanup(args) -> int:
    """Kill all persona tmux sessions for a panel run."""
    run_id = args.run_id
    config = _load_config(run_id)

    killed = []
    for persona, session in config.get("tmux_sessions", {}).items():
        if _tmux_session_exists(session):
            _tmux_cmd(["kill-session", "-t", session])
            killed.append(persona)

    config["status"] = "completed"
    _save_config(run_id, config)

    if args.json:
        print(json.dumps({"killed": killed}))
    else:
        if killed:
            print(f"Killed {len(killed)} sessions: {', '.join(killed)}")
        else:
            print("No active sessions to kill.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="panel_runner",
        description="Deterministic orchestration tool for solution discovery panels.",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p = sub.add_parser("init", help="Create panel directory and config")
    p.add_argument("--run-id", required=True, help="Unique panel run identifier")
    p.add_argument("--topic", required=True, help="The panel topic/question")
    p.add_argument("--preset", choices=["quick", "standard", "deep"], default=None)
    p.add_argument("--personas", default=None, help="Comma-separated persona names")
    p.add_argument("--persona-count", type=int, default=None, help="Number of personas to auto-select")
    p.add_argument("--rounds", type=int, default=None, help="Number of rounds")
    p.add_argument("--model", choices=["opus", "sonnet", "haiku"], default=None)
    p.add_argument("--json", action="store_true")

    # start-round
    p = sub.add_parser("start-round", help="Inject prompts for a round")
    p.add_argument("--run-id", required=True)
    p.add_argument("--round", required=True, type=int)
    p.add_argument("--synthesis", default=None, help="Path to synthesis from previous round")
    p.add_argument("--json", action="store_true")

    # check-round
    p = sub.add_parser("check-round", help="Check round completion")
    p.add_argument("--run-id", required=True)
    p.add_argument("--round", required=True, type=int)
    p.add_argument("--json", action="store_true")

    # collect
    p = sub.add_parser("collect", help="Collect round outputs into one document")
    p.add_argument("--run-id", required=True)
    p.add_argument("--round", required=True, type=int)
    p.add_argument("--json", action="store_true")

    # status
    p = sub.add_parser("status", help="Show panel status")
    p.add_argument("--run-id", required=True)
    p.add_argument("--json", action="store_true")

    # cleanup
    p = sub.add_parser("cleanup", help="Kill all persona sessions")
    p.add_argument("--run-id", required=True)
    p.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    dispatch = {
        "init": cmd_init,
        "start-round": cmd_start_round,
        "check-round": cmd_check_round,
        "collect": cmd_collect,
        "status": cmd_status,
        "cleanup": cmd_cleanup,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
