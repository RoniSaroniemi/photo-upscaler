#!/usr/bin/env python3
"""Workflow runner — executes deterministic workflow steps with optional agent judgment.

Usage:
    python3 tools/workflow_runner.py --workflow-dir .workflows/my-workflow --project-root . --run-id 20260325-090000-12345
    python3 tools/workflow_runner.py --workflow-dir .workflows/my-workflow --project-root . --run-id test --dry-run

Stdlib-only. No pip dependencies.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from tools.pid_lock import PidLock
except ImportError:
    import sys as _sys; _sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
    from pid_lock import PidLock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def emit(msg: str, **kv: object) -> None:
    parts = [msg] + [f"{k}={v}" for k, v in kv.items()]
    print(" | ".join(parts), flush=True)



# ---------------------------------------------------------------------------
# Step execution — script type
# ---------------------------------------------------------------------------

def run_script_step(step: dict, artifacts_dir: Path, workflow_dir: Path,
                    project_root: Path) -> dict:
    """Execute a script step. Returns result dict."""
    step_id = step["id"]
    command = step["command"]
    timeout = step.get("timeout_seconds", 300)

    stdout_path = artifacts_dir / f"step-{step_id}.stdout"
    stderr_path = artifacts_dir / f"step-{step_id}.stderr"

    started = time.time()
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(workflow_dir),
            timeout=timeout,
            capture_output=True,
            text=True,
            env={**os.environ, "PROJECT_ROOT": str(project_root),
                 "WORKFLOW_DIR": str(workflow_dir),
                 "ARTIFACTS_DIR": str(artifacts_dir)},
        )
        stdout_path.write_text(result.stdout)
        stderr_path.write_text(result.stderr)

        duration = time.time() - started
        if result.returncode != 0:
            return {
                "id": step_id, "status": "failed", "duration_seconds": round(duration, 1),
                "exit_code": result.returncode,
                "error": result.stderr[:500] if result.stderr else f"exit code {result.returncode}",
            }
        return {
            "id": step_id, "status": "success", "duration_seconds": round(duration, 1),
            "exit_code": 0,
        }
    except subprocess.TimeoutExpired:
        duration = time.time() - started
        return {
            "id": step_id, "status": "timeout", "duration_seconds": round(duration, 1),
            "error": f"Step timed out after {timeout}s",
        }
    except Exception as exc:
        duration = time.time() - started
        return {
            "id": step_id, "status": "failed", "duration_seconds": round(duration, 1),
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Step execution — agent type with enforced skill pattern
# ---------------------------------------------------------------------------

def run_agent_step(step: dict, artifacts_dir: Path, workflow_dir: Path,
                   project_root: Path) -> dict:
    """Execute an agent step with enforced terminal skill invocation."""
    step_id = step["id"]
    timeout = step.get("timeout_seconds", 180)
    max_attempts = step.get("max_attempts", 3)
    terminal_skills = step.get("terminal_skills", [])
    prompt_file = step.get("prompt_file", "")
    fallback = step.get("fallback", "escalate")
    requires = step.get("requires", [])

    # Build context from required artifacts
    context_parts = []
    for req in requires:
        req_path = artifacts_dir / req
        if req_path.exists():
            context_parts.append(f"--- {req} ---\n{req_path.read_text()}\n")

    # Load prompt template
    prompt_path = workflow_dir / prompt_file
    if prompt_path.exists():
        base_prompt = prompt_path.read_text()
    else:
        base_prompt = f"Analyze the provided data and choose an appropriate action."

    # Load terminal skill descriptions
    skill_descriptions = []
    for skill_name in terminal_skills:
        skill_md_path = workflow_dir / "skills" / skill_name / "SKILL.md"
        if skill_md_path.exists():
            skill_descriptions.append(f"### Skill: {skill_name}\n{skill_md_path.read_text()}")
        else:
            skill_descriptions.append(f"### Skill: {skill_name}\nNo description available.")

    skills_text = "\n\n".join(skill_descriptions)
    context_text = "\n".join(context_parts)
    action_path = artifacts_dir / "last-action.json"

    started = time.time()

    # Attempt 1: Normal prompt with skill descriptions
    attempt_results = []
    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            prompt = (
                f"{base_prompt}\n\n"
                f"## Data\n{context_text}\n\n"
                f"## Available Actions\n"
                f"You MUST choose exactly one of the following terminal skills and write "
                f"its output to last-action.json:\n\n{skills_text}\n\n"
                f"Write the JSON output to: {action_path}\n"
                f"Choose the most appropriate skill and invoke it now."
            )
        elif attempt == 2:
            prompt = (
                f"IMPORTANT: You did not produce a valid terminal skill output in your "
                f"previous response. You MUST write a JSON file to {action_path} with "
                f"one of these skills: {', '.join(terminal_skills)}.\n\n"
                f"## Data\n{context_text}\n\n"
                f"## Skills\n{skills_text}\n\n"
                f"Pick the most appropriate skill and write the output JSON NOW."
            )
        else:
            # Attempt 3: Simplified, direct
            prompt = (
                f"Given this data:\n{context_text[:2000]}\n\n"
                f"Choose exactly ONE action from: {', '.join(terminal_skills)}\n\n"
                f"Write a JSON file to {action_path} with this format:\n"
                f'{{"skill": "<chosen_skill>", "decided_at": "{now_iso()}", '
                f'"reasoning": "<one sentence>", "confidence": 0.8}}\n\n'
                f"Write the file now. Nothing else."
            )

        agent_result = _invoke_claude(prompt, timeout, artifacts_dir, step_id, attempt)
        attempt_results.append(agent_result)

        # Check if last-action.json was produced
        if action_path.exists():
            try:
                action_data = load_json(action_path)
                skill_used = action_data.get("skill", "")
                if skill_used in terminal_skills:
                    duration = time.time() - started
                    emit(f"agent_step_success", step=step_id, skill=skill_used,
                         attempt=attempt)
                    return {
                        "id": step_id, "status": "success",
                        "duration_seconds": round(duration, 1),
                        "agent_attempts": attempt, "skill_invoked": skill_used,
                    }
                else:
                    emit(f"agent_step_invalid_skill", step=step_id,
                         got=skill_used, expected=terminal_skills)
                    action_path.unlink()
            except (json.JSONDecodeError, OSError):
                emit(f"agent_step_bad_json", step=step_id, attempt=attempt)
                action_path.unlink(missing_ok=True)

        # Try to parse the agent output for a skill match
        parsed_skill = _parse_agent_output_for_skill(agent_result, terminal_skills)
        if parsed_skill:
            action_data = {
                "skill": parsed_skill,
                "decided_at": now_iso(),
                "reasoning": "Extracted from agent output (skill not formally invoked)",
                "confidence": 0.5,
                "source": f"parsed_attempt_{attempt}",
            }
            save_json(action_path, action_data)
            duration = time.time() - started
            emit(f"agent_step_parsed", step=step_id, skill=parsed_skill, attempt=attempt)
            return {
                "id": step_id, "status": "success",
                "duration_seconds": round(duration, 1),
                "agent_attempts": attempt, "skill_invoked": parsed_skill,
                "note": "skill parsed from output, not formally invoked",
            }

    # All attempts exhausted — fallback
    duration = time.time() - started
    if fallback == "escalate":
        _write_escalation(step, artifacts_dir, workflow_dir, project_root,
                          attempt_results)
    action_data = {
        "skill": "_escalated",
        "decided_at": now_iso(),
        "reasoning": f"All {max_attempts} attempts exhausted. Escalated.",
        "confidence": 0.0,
        "status": "escalated",
    }
    save_json(action_path, action_data)
    return {
        "id": step_id, "status": "escalated",
        "duration_seconds": round(duration, 1),
        "agent_attempts": max_attempts,
        "error": f"Agent failed to invoke a terminal skill after {max_attempts} attempts",
    }


def _invoke_claude(prompt: str, timeout: int, artifacts_dir: Path,
                   step_id: str, attempt: int) -> str:
    """Invoke claude CLI in non-interactive mode. Returns stdout."""
    prompt_file = artifacts_dir / f"step-{step_id}-attempt-{attempt}.prompt"
    output_file = artifacts_dir / f"step-{step_id}-attempt-{attempt}.output"

    prompt_file.write_text(prompt)

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text", "--max-turns", "1"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(artifacts_dir),
        )
        output = result.stdout or ""
        output_file.write_text(output)
        if result.stderr:
            (artifacts_dir / f"step-{step_id}-attempt-{attempt}.stderr").write_text(
                result.stderr)
        return output
    except subprocess.TimeoutExpired:
        output_file.write_text(f"TIMEOUT after {timeout}s")
        return ""
    except FileNotFoundError:
        output_file.write_text("ERROR: 'claude' CLI not found in PATH")
        return ""
    except Exception as exc:
        output_file.write_text(f"ERROR: {exc}")
        return ""


def _parse_agent_output_for_skill(output: str, terminal_skills: list[str]) -> str | None:
    """Try to find a skill name in the agent's text output."""
    if not output:
        return None
    output_lower = output.lower()
    # Look for skill names in the output
    for skill in terminal_skills:
        # Check for various patterns: "skill: no-action", "chose no-action", etc.
        if skill.lower() in output_lower:
            return skill
    # Try to parse JSON from the output
    try:
        # Find JSON-like content
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                data = json.loads(line)
                if data.get("skill") in terminal_skills:
                    return data["skill"]
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _write_escalation(step: dict, artifacts_dir: Path, workflow_dir: Path,
                      project_root: Path, attempt_results: list[str]) -> None:
    """Write an escalation file for the CPO to handle."""
    workflow_config = load_json(workflow_dir / "workflow.json")
    workflow_id = workflow_config.get("id", "unknown")
    run_id = artifacts_dir.name

    escalation_dir = project_root / ".cpo" / "escalations"
    escalation_dir.mkdir(parents=True, exist_ok=True)
    escalation_path = escalation_dir / f"workflow-{workflow_id}-{run_id}.md"

    content = [
        f"# Workflow Escalation\n",
        f"**Workflow:** {workflow_id}",
        f"**Run ID:** {run_id}",
        f"**Failed at:** {now_iso()}",
        f"**Step:** {step['id']} (agent)",
        f"**Attempts:** {step.get('max_attempts', 3)} exhausted\n",
        f"## Context",
        f"The agent was asked to choose between: {', '.join(step.get('terminal_skills', []))}\n",
        f"All attempts failed to invoke a terminal skill.\n",
        f"## Agent Outputs\n",
    ]
    for i, result in enumerate(attempt_results, 1):
        content.append(f"### Attempt {i}")
        content.append(f"```\n{result[:1000]}\n```\n")

    content.extend([
        f"## Required Action",
        f"Review the data at:\n  {artifacts_dir}/\n",
        f"Then either:",
        f"1. Manually create last-action.json with the decision",
        f"2. Fix the prompt/skills and re-run: {workflow_dir}/run.sh",
    ])

    escalation_path.write_text("\n".join(content))
    emit("escalation_written", path=str(escalation_path))


# ---------------------------------------------------------------------------
# Artifact retention
# ---------------------------------------------------------------------------

def cleanup_artifacts(workflow_dir: Path, retention_days: int,
                      retention_max_runs: int) -> int:
    """Delete old artifact directories. Returns number of directories removed."""
    artifacts_root = workflow_dir / "artifacts"
    if not artifacts_root.exists():
        return 0

    dirs = sorted(
        [d for d in artifacts_root.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    removed = 0
    cutoff_ts = time.time() - (retention_days * 86400)

    # Remove by age
    for d in dirs:
        try:
            # Parse date from run ID: YYYYMMDD-HHMMSS-PID
            date_str = d.name[:15]  # YYYYMMDD-HHMMSS
            dt = datetime.strptime(date_str, "%Y%m%d-%H%M%S")
            if dt.timestamp() < cutoff_ts:
                _rmtree(d)
                removed += 1
        except (ValueError, OSError):
            continue

    # Remove by count (keep most recent)
    dirs = sorted(
        [d for d in artifacts_root.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    if len(dirs) > retention_max_runs:
        for d in dirs[:-retention_max_runs]:
            _rmtree(d)
            removed += 1

    return removed


def _rmtree(path: Path) -> None:
    """Remove directory tree using stdlib only."""
    for child in path.iterdir():
        if child.is_dir():
            _rmtree(child)
        else:
            child.unlink()
    path.rmdir()


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def append_audit_log(workflow_dir: Path, entry: dict) -> None:
    """Append a JSONL entry to the audit log."""
    log_path = workflow_dir / "audit.log"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Registry update
# ---------------------------------------------------------------------------

def update_registry(project_root: Path, workflow_id: str,
                    run_result: dict) -> None:
    """Update the global workflow registry with the latest run result."""
    registry_path = project_root / ".workflows" / "registry.json"
    if not registry_path.exists():
        return

    registry = load_json(registry_path)
    workflows = registry.get("workflows", [])

    # Find or create entry
    entry = None
    for w in workflows:
        if w.get("id") == workflow_id:
            entry = w
            break

    if entry is None:
        entry = {"id": workflow_id, "enabled": True, "stats": {
            "total_runs": 0, "successes": 0, "failures": 0, "escalations": 0,
        }}
        workflows.append(entry)

    # Update last run
    entry["last_run"] = {
        "run_id": run_result.get("run_id"),
        "status": run_result.get("status"),
        "finished_at": run_result.get("finished_at"),
    }
    skill = run_result.get("skill_invoked")
    if skill:
        entry["last_run"]["skill_invoked"] = skill

    # Update stats
    stats = entry.get("stats", {
        "total_runs": 0, "successes": 0, "failures": 0, "escalations": 0,
    })
    stats["total_runs"] = stats.get("total_runs", 0) + 1
    status = run_result.get("status", "failed")
    if status == "success":
        stats["successes"] = stats.get("successes", 0) + 1
    elif status == "escalated":
        stats["escalations"] = stats.get("escalations", 0) + 1
    else:
        stats["failures"] = stats.get("failures", 0) + 1
        stats["last_failure_at"] = run_result.get("finished_at")
    entry["stats"] = stats

    registry["workflows"] = workflows
    save_json(registry_path, registry)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def send_notifications(project_root: Path, workflow_config: dict,
                       run_result: dict) -> None:
    """Send success/failure notifications via configured channels."""
    status = run_result.get("status", "failed")
    notif_config = workflow_config.get("notifications", {})

    if status == "success":
        notif = notif_config.get("on_success", {})
    else:
        notif = notif_config.get("on_failure", {})

    if not notif:
        return

    template = notif.get("message_template", "Workflow completed")
    message = template.format(
        name=workflow_config.get("name", workflow_config.get("id", "unknown")),
        summary=_run_summary(run_result),
        failed_step=run_result.get("failed_step", ""),
        error=run_result.get("error", ""),
        status=status,
    )

    # Slack notification
    if notif.get("slack"):
        slack_config = project_root / ".agent-comms" / "slack.json"
        if slack_config.exists():
            try:
                subprocess.run(
                    ["python3", str(project_root / "tools" / "agent_slack.py"),
                     "--project-config", str(slack_config),
                     "send", "--role", "CPO", "--message", message],
                    capture_output=True, text=True, timeout=30,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
                emit("notification_failed", channel="slack", error=str(exc))

    # Telegram notification
    if notif.get("telegram"):
        tg_config = project_root / ".agent-comms" / "telegram.json"
        if tg_config.exists():
            try:
                subprocess.run(
                    ["python3", str(project_root / "tools" / "agent_telegram.py"),
                     "--project-config", str(tg_config),
                     "send", "--role", "CPO", "--message", message],
                    capture_output=True, text=True, timeout=30,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
                emit("notification_failed", channel="telegram", error=str(exc))


def _run_summary(run_result: dict) -> str:
    """Generate a short summary of a workflow run."""
    status = run_result.get("status", "unknown")
    duration = run_result.get("duration_seconds", 0)
    skill = run_result.get("skill_invoked", "")
    parts = [status]
    if skill:
        parts.append(f"action={skill}")
    parts.append(f"{duration}s")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_workflow(workflow_dir: Path, project_root: Path, run_id: str,
                 dry_run: bool = False) -> dict:
    """Execute all steps in a workflow. Returns the run result."""
    config_path = workflow_dir / "workflow.json"
    if not config_path.exists():
        emit("error", msg=f"workflow.json not found in {workflow_dir}")
        return {"status": "failed", "error": "workflow.json not found"}

    config = load_json(config_path)
    workflow_id = config.get("id", "unknown")
    steps = config.get("steps", [])

    if not config.get("enabled", False):
        emit("workflow_disabled", id=workflow_id)
        return {"status": "skipped", "reason": "workflow disabled"}

    emit(f"workflow_start", id=workflow_id, run_id=run_id, steps=len(steps))

    if dry_run:
        emit("dry_run", msg="Validated config, would execute steps",
             steps=[s["id"] for s in steps])
        return {"status": "dry_run", "run_id": run_id, "workflow_id": workflow_id}

    # Create artifacts directory
    artifacts_dir = workflow_dir / "artifacts" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Lock
    lock_path = workflow_dir / "artifacts" / ".lock"
    lock = PidLock(str(lock_path))
    if not lock.acquire(blocking=False):
        emit("workflow_locked", id=workflow_id)
        return {"status": "skipped", "reason": "another run is in progress"}

    started_at = now_iso()
    start_time = time.time()
    step_results = []
    overall_status = "success"
    failed_step = ""
    error_msg = ""
    skill_invoked = ""

    try:
        for step in steps:
            step_id = step["id"]
            step_type = step.get("type", "script")

            # Check that required files exist
            for req in step.get("requires", []):
                req_path = artifacts_dir / req
                if not req_path.exists():
                    emit("missing_requirement", step=step_id, file=req)
                    step_results.append({
                        "id": step_id, "status": "failed",
                        "error": f"Required file not found: {req}",
                    })
                    overall_status = "failed"
                    failed_step = step_id
                    error_msg = f"Required file not found: {req}"
                    break

            if overall_status == "failed":
                break

            emit(f"step_start", step=step_id, type=step_type)

            if step_type == "script":
                result = run_script_step(step, artifacts_dir, workflow_dir,
                                         project_root)
            elif step_type == "agent":
                result = run_agent_step(step, artifacts_dir, workflow_dir,
                                        project_root)
            else:
                result = {"id": step_id, "status": "failed",
                          "error": f"Unknown step type: {step_type}"}

            step_results.append(result)
            emit(f"step_done", step=step_id, status=result["status"])

            if result["status"] not in ("success",):
                overall_status = result["status"]
                failed_step = step_id
                error_msg = result.get("error", "")
                if result.get("skill_invoked"):
                    skill_invoked = result["skill_invoked"]
                break

            if result.get("skill_invoked"):
                skill_invoked = result["skill_invoked"]

    finally:
        lock.release()

    duration = round(time.time() - start_time, 1)
    finished_at = now_iso()

    run_result = {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "status": overall_status,
        "steps": step_results,
    }
    if failed_step:
        run_result["failed_step"] = failed_step
    if error_msg:
        run_result["error"] = error_msg
    if skill_invoked:
        run_result["skill_invoked"] = skill_invoked

    # Write last-run.json
    save_json(workflow_dir / "last-run.json", run_result)

    # Append to audit log
    append_audit_log(workflow_dir, run_result)

    # Update global registry
    update_registry(project_root, workflow_id, run_result)

    # Send notifications
    send_notifications(project_root, config, run_result)

    # Artifact retention
    retention = config.get("artifacts", {})
    removed = cleanup_artifacts(
        workflow_dir,
        retention.get("retention_days", 30),
        retention.get("retention_max_runs", 100),
    )
    if removed > 0:
        emit("artifacts_cleaned", removed=removed)

    emit(f"workflow_done", id=workflow_id, status=overall_status,
         duration=f"{duration}s")
    return run_result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute a workflow defined in workflow.json")
    parser.add_argument("--workflow-dir", required=True,
                        help="Path to the workflow directory")
    parser.add_argument("--project-root", required=True,
                        help="Path to the project root")
    parser.add_argument("--run-id", required=True,
                        help="Unique run identifier (e.g., YYYYMMDD-HHMMSS-PID)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate config without executing steps")

    args = parser.parse_args()

    workflow_dir = Path(args.workflow_dir).resolve()
    project_root = Path(args.project_root).resolve()

    result = run_workflow(workflow_dir, project_root, args.run_id,
                          dry_run=args.dry_run)

    status = result.get("status", "failed")
    if status in ("success", "dry_run", "skipped"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
