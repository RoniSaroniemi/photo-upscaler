"""Queue daemon — persistent process managing the queue dispatch loop.

Replaces agent-driven cron for continuous mode. Polls SQLite, claims items,
dispatches workers via codex/claude exec, collects results, triggers the
Method Analyst for deep artifact review, and triggers the Queue Director
for learning reviews when needed.

Commands:
    run    — Start the daemon (foreground, PID-locked)
    status — Print current daemon-status.json
    stop   — Send SIGTERM to a running daemon
"""

import argparse
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Import PidLock from sibling module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pid_lock import PidLock

DAEMON_VERSION = "1.1.0"


class QueueDaemon:
    """Core daemon that manages the queue dispatch loop."""

    def __init__(self, config_path: str):
        self.config_path = os.path.abspath(config_path)
        self.config = self._load_config()
        self.queue_dir = Path(self.config_path).parent
        self.db_path = self.queue_dir / "queue.db"
        self.state_dir = Path(__file__).resolve().parent.parent / "state"
        self.status_path = self.state_dir / "daemon-status.json"
        self.lock_path = self.state_dir / f"daemon-{self.config['queue_id']}.lock"

        # Daemon config (with defaults)
        daemon_cfg = self.config.get("daemon", {})
        self.poll_interval = daemon_cfg.get("poll_interval_seconds", 30)
        self.mode = daemon_cfg.get("mode", "passive")
        self.director_session = daemon_cfg.get("director_session", "director")

        # Concurrency config
        cc = self.config.get("concurrency", {})
        self.max_workers = cc.get("max_workers", 2)
        self.worker_provider = cc.get("worker_provider", "codex")
        self.worker_timeout = cc.get("worker_timeout_minutes", 10) * 60  # seconds

        # Budget config
        budget = self.config.get("budget", {})
        self.max_items_per_day = budget.get("max_items_per_day", 100)

        # Learning config — use daemon override or fall back to learning section
        learning = self.config.get("learning", {})
        self.review_interval = daemon_cfg.get(
            "director_review_interval",
            learning.get("review_interval_continuous", 20),
        )

        # Discovery config
        discovery = self.config.get("discovery", {})
        self.discovery_enabled = discovery.get("enabled", False)
        self.discovery_threshold = discovery.get("trigger_threshold", 10)
        self.discovery_batch_size = discovery.get("batch_size", 20)
        self.discovery_max_attempts = discovery.get("max_discovery_attempts", 3)
        self.max_queue_size = budget.get("max_queue_size", 1000)

        # Method Analyst config
        analyst_cfg = self.config.get("analyst", {})
        self.analyst_enabled = analyst_cfg.get("enabled", True)
        self.analyst_timeout = analyst_cfg.get("timeout_seconds", 300)
        self.analyst_provider = analyst_cfg.get("provider", self.worker_provider)
        self.analyst_prompt_path = self.queue_dir / "method-analyst-prompt.md"
        # Fall back to template if queue-specific prompt doesn't exist
        if not self.analyst_prompt_path.exists():
            template_prompt = (
                Path(__file__).resolve().parent.parent
                / ".operations" / "queue-template" / "method-analyst-prompt.md"
            )
            if template_prompt.exists():
                self.analyst_prompt_path = template_prompt

        # Runtime state
        self.workers = {}  # pid -> {item_id, artifact_path, started_at, process, worker_id}
        self.items_since_review = 0
        self.running = False
        self.learning_in_progress = False
        self.analyst_in_progress = False
        self.analyst_process = None  # subprocess.Popen for analyst
        self.analyst_started_at = None
        self.learning_signal_path = self.queue_dir / "learning-complete.signal"
        self.discovery_in_progress = False
        self.discovery_process = None
        self.discovery_attempts = 0

        # Logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [daemon] %(message)s",
            datefmt="%H:%M:%S",
        )
        self.log = logging.getLogger("queue-daemon")

    # -- helpers ---------------------------------------------------------

    def _load_config(self) -> dict:
        with open(self.config_path) as f:
            return json.load(f)

    def _db_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _queue_runner(self, *args) -> subprocess.CompletedProcess:
        """Run queue_runner.py with the current config."""
        runner = str(Path(__file__).resolve().parent / "queue_runner.py")
        cmd = [sys.executable, runner] + list(args) + ["--config", self.config_path]
        return subprocess.run(cmd, capture_output=True, text=True)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # -- core loop steps -------------------------------------------------

    def _check_timeouts(self):
        """Mark orphaned claimed items that exceeded the worker timeout."""
        tracked_items = {info["item_id"] for info in self.workers.values()}
        conn = self._db_connect()
        now = datetime.now(timezone.utc)

        rows = conn.execute(
            "SELECT item_id, claimed_at FROM items WHERE status = 'claimed'"
        ).fetchall()
        conn.close()

        for row in rows:
            if row["item_id"] in tracked_items:
                continue  # handled by _check_workers
            claimed_at = row["claimed_at"]
            if not claimed_at:
                continue
            try:
                claimed = datetime.strptime(claimed_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
            elapsed = (now - claimed).total_seconds()
            if elapsed > self.worker_timeout:
                self.log.warning(
                    "Orphaned item %s timed out (%.0fs)", row["item_id"], elapsed
                )
                self._queue_runner(
                    "fail",
                    "--item-id", row["item_id"],
                    "--error", f"Orphaned item timed out after {int(elapsed)}s",
                )

    def _get_queue_counts(self) -> dict:
        """Return {ready, claimed, completed, failed, total} from the DB."""
        result = self._queue_runner("status", "--json")
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {}

    def _dispatch_worker(self):
        """Claim one item and launch a worker process for it."""
        worker_id = f"daemon-w{int(time.time()) % 100000}"

        result = self._queue_runner("claim", "--worker-id", worker_id, "--json")
        if result.returncode != 0:
            return  # no ready items

        item = json.loads(result.stdout)
        item_id = item["item_id"]
        custom_data = item.get("custom_data", {})
        if isinstance(custom_data, str):
            custom_data = json.loads(custom_data)

        # Artifact path
        artifacts_dir = self.queue_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        artifact_path = str(artifacts_dir / f"{item_id}.json")

        # Build prompt from executor-prompt.md + item data
        prompt_path = self.queue_dir / "executor-prompt.md"
        if prompt_path.exists():
            executor_prompt = prompt_path.read_text()
        else:
            executor_prompt = "Process the item and write the artifact."

        item_json = json.dumps(custom_data, indent=2)
        full_prompt = (
            f"{executor_prompt}\n\n"
            f"Item ID: {item_id}\n"
            f"Item data:\n{item_json}\n\n"
            f"Write artifact to: {artifact_path}"
        )

        # Build provider command
        if self.worker_provider == "codex":
            cmd = [
                "codex", "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                full_prompt,
            ]
        else:
            cmd = [
                "claude", "-p",
                "--dangerously-skip-permissions",
                full_prompt,
            ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=str(self.queue_dir),
            )
            self.workers[proc.pid] = {
                "item_id": item_id,
                "artifact_path": artifact_path,
                "started_at": time.time(),
                "process": proc,
                "worker_id": worker_id,
            }
            self.log.info("Dispatched worker PID %d for %s", proc.pid, item_id)
        except Exception as e:
            self.log.error("Failed to dispatch worker for %s: %s", item_id, e)
            self._queue_runner(
                "fail", "--item-id", item_id, "--error", f"Dispatch failed: {e}"
            )

    def _check_workers(self):
        """Poll tracked worker processes for completion or timeout."""
        finished = []
        for pid, info in self.workers.items():
            proc = info["process"]
            retcode = proc.poll()

            if retcode is None:
                # Still running — check timeout
                if time.time() - info["started_at"] > self.worker_timeout:
                    self.log.warning("Worker PID %d timed out, killing", pid)
                    proc.kill()
                    proc.wait()
                    # Check if artifact was written before the timeout
                    if os.path.exists(info["artifact_path"]):
                        self._queue_runner(
                            "complete",
                            "--item-id", info["item_id"],
                            "--artifact-path", info["artifact_path"],
                        )
                        self.items_since_review += 1
                        self.log.info(
                            "Worker PID %d timed out but artifact exists — completing %s",
                            pid, info["item_id"],
                        )
                    else:
                        self._queue_runner(
                            "fail",
                            "--item-id", info["item_id"],
                            "--error", "Worker process timed out",
                        )
                    finished.append(pid)
                continue

            # Process exited
            artifact_exists = os.path.exists(info["artifact_path"])

            if retcode == 0 and artifact_exists:
                self._queue_runner(
                    "complete",
                    "--item-id", info["item_id"],
                    "--artifact-path", info["artifact_path"],
                )
                self.items_since_review += 1
                self.log.info("Worker PID %d completed %s", pid, info["item_id"])
            else:
                # Read up to 500 chars of stderr for error context
                stderr_text = ""
                try:
                    stderr_text = proc.stderr.read(500).decode("utf-8", errors="replace")
                except Exception:
                    pass
                if retcode == 0:
                    error = "exit=0 but no artifact found"
                else:
                    error = f"exit={retcode}"
                    if stderr_text:
                        error += f" {stderr_text.strip()[:200]}"
                self._queue_runner(
                    "fail",
                    "--item-id", info["item_id"],
                    "--error", error,
                )
                self.log.warning("Worker PID %d failed %s: %s", pid, info["item_id"], error)

            finished.append(pid)

        for pid in finished:
            del self.workers[pid]

    # -- method analyst ----------------------------------------------------

    def _get_next_proposal_number(self) -> int:
        """Determine the next proposal number from existing proposal files."""
        methods_dir = self.queue_dir / "methods"
        if not methods_dir.exists():
            return 1
        existing = sorted(methods_dir.glob("proposal-*.md"))
        if not existing:
            return 1
        # Extract highest N from proposal-N.md
        nums = []
        for p in existing:
            try:
                n = int(p.stem.split("-")[1])
                nums.append(n)
            except (IndexError, ValueError):
                pass
        return max(nums, default=0) + 1

    def _get_recent_artifacts(self, n: int) -> list[dict]:
        """Load the last N completed artifacts sorted by processed_at."""
        artifacts_dir = self.queue_dir / "artifacts"
        if not artifacts_dir.exists():
            return []
        artifact_files = sorted(artifacts_dir.glob("ITEM-*.json"))
        loaded = []
        for af in artifact_files:
            try:
                data = json.loads(af.read_text())
                loaded.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        # Sort by processed_at descending, take last N
        loaded.sort(
            key=lambda a: a.get("metadata", {}).get("processed_at", ""),
            reverse=True,
        )
        return loaded[:n]

    def _get_iteration_notes(self) -> str:
        """Concatenate all iteration-*.md files from methods/."""
        methods_dir = self.queue_dir / "methods"
        if not methods_dir.exists():
            return "(no previous iteration notes)"
        notes = []
        for f in sorted(methods_dir.glob("iteration-*.md")):
            try:
                notes.append(f.read_text())
            except OSError:
                continue
        return "\n\n---\n\n".join(notes) if notes else "(no previous iteration notes)"

    def _build_analyst_prompt(self, artifacts: list[dict], proposal_n: int) -> str:
        """Build the full analyst prompt with injected context."""
        # Load the analyst prompt template
        if self.analyst_prompt_path.exists():
            template = self.analyst_prompt_path.read_text()
        else:
            template = "Analyze the artifacts and write a proposal."

        # Load current executor prompt
        executor_path = self.queue_dir / "executor-prompt.md"
        executor_prompt = "(no executor prompt found)"
        if executor_path.exists():
            executor_prompt = executor_path.read_text()

        # Load artifact schema from queue config
        artifact_schema = json.dumps(
            self.config.get("artifact_schema", {}), indent=2
        )

        # Load iteration notes
        iteration_notes = self._get_iteration_notes()

        # Format artifacts
        artifacts_json = json.dumps(artifacts, indent=2)

        # Replace placeholders in template
        queue_name = self.config.get("name", self.config.get("queue_id", "unknown"))
        prompt = template
        prompt = prompt.replace("[QUEUE_NAME]", queue_name)
        prompt = prompt.replace("[EXECUTOR_PROMPT]", executor_prompt)
        prompt = prompt.replace("[ARTIFACT_SCHEMA]", artifact_schema)
        prompt = prompt.replace("[ITERATION_NOTES]", iteration_notes)
        prompt = prompt.replace("[ARTIFACTS]", artifacts_json)
        prompt = prompt.replace("[N]", str(proposal_n))
        prompt = prompt.replace("[DATE]", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        # Append concrete output paths
        methods_dir = self.queue_dir / "methods"
        prompt += (
            f"\n\n## Output Paths\n\n"
            f"Write your proposal to: {methods_dir}/proposal-{proposal_n}.md\n"
            f"Write/append source memory to: {methods_dir}/source-memory-updates.md\n"
            f"Write per-item source memory to: {methods_dir}/source-memory-items-{proposal_n}.json\n"
            f"Queue directory: {self.queue_dir}\n"
        )

        return prompt

    def _trigger_method_analyst(self):
        """Launch the Method Analyst as a subprocess to analyze recent artifacts."""
        n = self.items_since_review or self.review_interval
        artifacts = self._get_recent_artifacts(n)
        if not artifacts:
            self.log.warning("No artifacts found for analyst review")
            return

        proposal_n = self._get_next_proposal_number()
        prompt = self._build_analyst_prompt(artifacts, proposal_n)

        # Ensure methods dir exists
        methods_dir = self.queue_dir / "methods"
        methods_dir.mkdir(exist_ok=True)

        # Launch analyst process
        if self.analyst_provider == "codex":
            cmd = [
                "codex", "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                prompt,
            ]
        else:
            cmd = [
                "claude", "-p",
                "--dangerously-skip-permissions",
                prompt,
            ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.queue_dir),
            )
            self.analyst_process = proc
            self.analyst_started_at = time.time()
            self.analyst_in_progress = True
            self.log.info(
                "Launched Method Analyst PID %d (proposal-%d, %d artifacts)",
                proc.pid, proposal_n, len(artifacts),
            )
        except Exception as e:
            self.log.error("Failed to launch Method Analyst: %s", e)
            # Fall back to direct director review
            self._trigger_director_review()

    def _persist_source_memory(self, proposal_n: int):
        """Write per-item source memory entries from analyst output to the DB."""
        sm_path = self.queue_dir / "methods" / f"source-memory-items-{proposal_n}.json"
        if not sm_path.exists():
            self.log.info("No per-item source memory file at %s", sm_path.name)
            return

        try:
            entries = json.loads(sm_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            self.log.warning("Failed to parse %s: %s", sm_path.name, e)
            return

        if not isinstance(entries, list):
            self.log.warning("source-memory-items-%d.json is not a JSON array", proposal_n)
            return

        persisted = 0
        for entry in entries:
            item_id = entry.get("item_id")
            sm_data = entry.get("source_memory")
            if not item_id or not sm_data:
                continue

            result = self._queue_runner(
                "update-source-memory",
                "--item-id", item_id,
                "--json", json.dumps(sm_data),
            )
            if result.returncode == 0:
                persisted += 1
            else:
                self.log.warning(
                    "Failed to persist source memory for %s: %s",
                    item_id, result.stderr.strip()[:200],
                )

        self.log.info(
            "Persisted source memory for %d/%d items from %s",
            persisted, len(entries), sm_path.name,
        )

    def _check_analyst_progress(self):
        """Check if the analyst subprocess has completed."""
        if not self.analyst_in_progress or self.analyst_process is None:
            return

        retcode = self.analyst_process.poll()

        if retcode is None:
            # Still running — check timeout
            elapsed = time.time() - self.analyst_started_at
            if elapsed > self.analyst_timeout:
                self.log.warning("Method Analyst timed out after %.0fs, killing", elapsed)
                self.analyst_process.kill()
                self.analyst_process.wait()
                self.analyst_in_progress = False
                self.analyst_process = None
                # Fall back to standard director review
                self._trigger_director_review()
            return

        # Analyst finished
        self.analyst_in_progress = False
        self.analyst_process = None

        if retcode == 0:
            # Check if proposal file was written
            proposal_n = self._get_next_proposal_number() - 1  # just wrote it
            proposal_path = self.queue_dir / "methods" / f"proposal-{proposal_n}.md"
            if not proposal_path.exists():
                # Try current number (analyst may not have incremented)
                proposal_path = self.queue_dir / "methods" / f"proposal-{proposal_n + 1}.md"

            # Persist per-item source memory to DB
            self._persist_source_memory(proposal_n)

            if proposal_path.exists():
                self.log.info("Method Analyst produced %s", proposal_path.name)
                self._trigger_director_review(proposal_path=proposal_path)
            else:
                self.log.warning(
                    "Method Analyst exited 0 but no proposal file found, "
                    "triggering standard director review"
                )
                self._trigger_director_review()
        else:
            stderr_text = ""
            try:
                stderr_text = self.analyst_process.stderr.read(500).decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                pass
            self.log.warning(
                "Method Analyst failed (exit=%d): %s", retcode, stderr_text[:200]
            )
            # Fall back to standard director review
            self._trigger_director_review()

    def _check_learning_trigger(self):
        """Trigger a learning review when the threshold is reached.

        Two-phase flow when analyst is enabled:
        1. Analyst runs first → produces proposal-N.md
        2. Director reviews proposal → writes decision → updates prompt
        """
        if self.mode == "off":
            return

        # Phase 2: check if analyst is running
        if self.analyst_in_progress:
            self._check_analyst_progress()
            return

        if self.learning_in_progress:
            # Check for completion signal (file-based, more reliable than tmux polling)
            if self.learning_signal_path.exists():
                try:
                    self.learning_signal_path.unlink()
                except OSError:
                    pass
                self.learning_in_progress = False
                self.items_since_review = 0
                self.log.info("Learning review complete, resuming dispatches")
                # Reload config in case executor-prompt changed
                self.config = self._load_config()
            return

        if self.items_since_review >= self.review_interval:
            self.log.info(
                "Learning trigger: %d items since last review (threshold=%d)",
                self.items_since_review,
                self.review_interval,
            )
            if self.analyst_enabled:
                self._trigger_method_analyst()
            else:
                self._trigger_director_review()

    def _trigger_director_review(self, proposal_path: Path = None):
        """Inject a learning review prompt into the director's tmux session.

        If proposal_path is provided (from Method Analyst), the director reviews
        the proposal and writes a decision. Otherwise, falls back to the standard
        artifact-based review.
        """
        self.learning_in_progress = True

        # Clear stale signal
        if self.learning_signal_path.exists():
            try:
                self.learning_signal_path.unlink()
            except OSError:
                pass

        if proposal_path and proposal_path.exists():
            # Analyst-driven review: director reviews the proposal
            decision_name = proposal_path.stem.replace("proposal", "decision")
            decision_path = proposal_path.parent / f"{decision_name}.md"
            review_prompt = (
                f"Method Analyst proposal ready for review. "
                f"Read the proposal at {proposal_path} and decide which changes to apply. "
                f"For each proposed change, decide: approve / reject / modify. "
                f"Write your decision to {decision_path} with this format:\n\n"
                f"# Director Decision — {proposal_path.stem}\n\n"
                f"## Changes Applied\n"
                f"[List each approved change and what you modified in executor-prompt.md]\n\n"
                f"## Changes Rejected\n"
                f"[List rejected changes with reasons]\n\n"
                f"## Notes\n"
                f"[Any additional observations]\n\n"
                f"If you approve any prompt changes, update {self.queue_dir}/executor-prompt.md accordingly. "
                f"When done, create the file {self.learning_signal_path} with "
                f"content 'done' to signal completion."
            )
        else:
            # Standard review (no analyst)
            review_prompt = (
                f"Learning review triggered by queue daemon. "
                f"{self.items_since_review} items completed since last review. "
                f"Read the last {self.items_since_review} artifacts in "
                f"{self.queue_dir}/artifacts/ and update "
                f"{self.queue_dir}/executor-prompt.md with any improvements. "
                f"When done, create the file {self.learning_signal_path} with "
                f"content 'done' to signal completion."
            )

        # Try tmux injection via codex_adapter
        adapter = str(Path(__file__).resolve().parent / "codex_adapter.py")
        result = subprocess.run(
            [
                sys.executable, adapter, "inject",
                "--session", self.director_session,
                "--prompt", review_prompt,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            self.log.warning(
                "Could not inject into director session '%s': %s",
                self.director_session,
                result.stderr.strip(),
            )
            # Fallback: write request file for manual pickup
            request_file = self.queue_dir / "learning-review-request.md"
            request_file.write_text(review_prompt + "\n")
            self.log.info("Wrote review request to %s", request_file)

    def _check_health(self) -> dict:
        """Run health checks and return {status, issues}."""
        counts = self._get_queue_counts()
        issues = []

        # Daily budget
        completed = counts.get("completed", 0)
        if completed >= self.max_items_per_day:
            issues.append(f"daily_budget_exceeded ({completed}/{self.max_items_per_day})")

        # Error rate
        total = counts.get("total", 0)
        failed = counts.get("failed", 0)
        if total > 5 and failed > 0 and (failed / total) > 0.5:
            issues.append(f"high_error_rate ({failed}/{total})")

        # Queue exhausted
        if counts.get("ready", 0) == 0 and len(self.workers) == 0:
            issues.append("queue_exhausted")

        return {"status": counts, "issues": issues}

    def _check_discovery_trigger(self, health: dict):
        """Trigger discovery when ready items fall below threshold."""
        if not self.discovery_enabled:
            return

        # Check if discovery process is still running
        if self.discovery_in_progress and self.discovery_process:
            retcode = self.discovery_process.poll()
            if retcode is None:
                return  # still running
            # Process finished
            self.discovery_in_progress = False
            if retcode == 0:
                self.log.info("Discovery completed successfully")
                self.discovery_attempts = 0
                # Reload config in case it changed
                self.config = self._load_config()
            else:
                stderr = ""
                try:
                    stderr = self.discovery_process.stderr.read(500)
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode("utf-8", errors="replace")
                except Exception:
                    pass
                self.log.warning(
                    "Discovery failed (exit=%d): %s", retcode, stderr.strip()[:200]
                )
            self.discovery_process = None
            return

        # Should we trigger discovery?
        counts = health.get("status", {})
        ready = counts.get("ready", 0)
        total = counts.get("total", 0)

        if ready >= self.discovery_threshold:
            return  # enough ready items
        if total >= self.max_queue_size:
            return  # queue is full
        if self.discovery_attempts >= self.discovery_max_attempts:
            return  # too many attempts this session
        if self.learning_in_progress:
            return  # wait for learning to finish

        self.log.info(
            "Discovery trigger: ready=%d < threshold=%d (total=%d, attempt %d/%d)",
            ready,
            self.discovery_threshold,
            total,
            self.discovery_attempts + 1,
            self.discovery_max_attempts,
        )
        self._launch_discovery()

    def _launch_discovery(self):
        """Launch the discovery runner as a subprocess."""
        self.discovery_in_progress = True
        self.discovery_attempts += 1

        runner = str(Path(__file__).resolve().parent / "discovery_runner.py")
        cmd = [
            sys.executable,
            runner,
            "--config",
            self.config_path,
            "--batch-size",
            str(self.discovery_batch_size),
            "--json",
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(Path(__file__).resolve().parent.parent),
            )
            self.discovery_process = proc
            self.log.info("Launched discovery (PID %d, batch_size=%d)",
                          proc.pid, self.discovery_batch_size)
        except Exception as e:
            self.log.error("Failed to launch discovery: %s", e)
            self.discovery_in_progress = False

    def _write_status(self, health: dict):
        """Atomically write daemon state to state/daemon-status.json."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "daemon_version": DAEMON_VERSION,
            "queue_id": self.config.get("queue_id", "unknown"),
            "config_path": self.config_path,
            "mode": self.mode,
            "pid": os.getpid(),
            "running": self.running,
            "poll_interval_seconds": self.poll_interval,
            "max_workers": self.max_workers,
            "active_workers": len(self.workers),
            "items_since_review": self.items_since_review,
            "learning_in_progress": self.learning_in_progress,
            "discovery_in_progress": self.discovery_in_progress,
            "discovery_attempts": self.discovery_attempts,
            "analyst_in_progress": self.analyst_in_progress,
            "analyst_pid": (
                self.analyst_process.pid
                if self.analyst_process and self.analyst_process.poll() is None
                else None
            ),
            "queue_status": health.get("status", {}),
            "health_issues": health.get("issues", []),
            "worker_pids": [
                {
                    "pid": pid,
                    "item_id": info["item_id"],
                    "elapsed_s": int(time.time() - info["started_at"]),
                }
                for pid, info in self.workers.items()
            ],
            "updated_at": self._now_iso(),
        }
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        os.replace(str(tmp), str(self.status_path))

    def _should_dispatch(self, health: dict) -> bool:
        """Return True if we should dispatch another worker this tick."""
        if self.mode == "active":
            return False  # director manages dispatch in active mode
        if (self.learning_in_progress or self.analyst_in_progress) and self.mode != "off":
            return False
        if any("budget_exceeded" in i for i in health.get("issues", [])):
            return False
        if health.get("status", {}).get("ready", 0) == 0:
            return False
        if len(self.workers) >= self.max_workers:
            return False
        return True

    # -- main loop -------------------------------------------------------

    def _tick(self):
        """Single iteration of the daemon loop."""
        self._check_timeouts()
        self._check_workers()
        self._check_learning_trigger()

        health = self._check_health()
        self._check_discovery_trigger(health)

        # Dispatch workers up to max_workers
        dispatched = 0
        while self._should_dispatch(health):
            prev_count = len(self.workers)
            self._dispatch_worker()
            if len(self.workers) == prev_count:
                break  # no item was claimed (queue empty or error)
            dispatched += 1
            health = self._check_health()

        if dispatched:
            self.log.info("Dispatched %d worker(s) this tick", dispatched)

        self._write_status(health)

    def run(self):
        """Start the daemon loop (blocks until stopped)."""
        lock = PidLock(str(self.lock_path))
        if not lock.acquire():
            print(
                f"Another daemon is already running (lock: {self.lock_path})",
                file=sys.stderr,
            )
            sys.exit(1)

        self.running = True
        self.log.info(
            "Queue daemon started (queue=%s, mode=%s, poll=%ds, max_workers=%d)",
            self.config.get("queue_id"),
            self.mode,
            self.poll_interval,
            self.max_workers,
        )

        # Handle SIGTERM for graceful shutdown
        original_sigterm = signal.getsignal(signal.SIGTERM)

        def _handle_sigterm(signum, frame):
            self.log.info("Received SIGTERM, shutting down")
            self.running = False

        signal.signal(signal.SIGTERM, _handle_sigterm)

        try:
            while self.running:
                try:
                    self._tick()
                except Exception as e:
                    self.log.error("Tick error: %s", e)

                # Sleep in 1-second increments for responsive shutdown
                for _ in range(self.poll_interval):
                    if not self.running:
                        break
                    time.sleep(1)
        except KeyboardInterrupt:
            self.log.info("Interrupted")
        finally:
            self.running = False
            self._cleanup_workers()
            self._write_status(
                {"status": self._get_queue_counts(), "issues": ["daemon_stopped"]}
            )
            lock.release()
            signal.signal(signal.SIGTERM, original_sigterm)
            self.log.info("Daemon stopped")

    def _cleanup_workers(self):
        """Kill all running workers and analyst on shutdown."""
        for pid, info in list(self.workers.items()):
            proc = info["process"]
            if proc.poll() is None:
                self.log.info("Killing worker PID %d (%s)", pid, info["item_id"])
                proc.kill()
                proc.wait()
        if self.analyst_process and self.analyst_process.poll() is None:
            self.log.info("Killing Method Analyst PID %d", self.analyst_process.pid)
            self.analyst_process.kill()
            self.analyst_process.wait()


# -- CLI -----------------------------------------------------------------


def cmd_run(args):
    daemon = QueueDaemon(args.config)
    daemon.run()


def cmd_status(args):
    state_dir = Path(__file__).resolve().parent.parent / "state"
    status_path = state_dir / "daemon-status.json"
    if not status_path.exists():
        print("No daemon status file found.")
        sys.exit(1)
    data = json.loads(status_path.read_text())
    print(json.dumps(data, indent=2))


def cmd_stop(args):
    state_dir = Path(__file__).resolve().parent.parent / "state"
    config = json.loads(Path(args.config).read_text())
    lock_path = state_dir / f"daemon-{config['queue_id']}.lock"
    if not lock_path.exists():
        print("No daemon running (no lock file).")
        sys.exit(1)
    try:
        pid = int(lock_path.read_text().strip())
    except (ValueError, OSError) as e:
        print(f"Cannot read lock file: {e}")
        sys.exit(1)
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to daemon PID {pid}")
    except ProcessLookupError:
        print(f"Daemon PID {pid} not running, removing stale lock.")
        lock_path.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Queue daemon — persistent dispatch loop",
    )
    parser.add_argument("--config", help="Path to queue.json")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Start the daemon")
    sub.add_parser("status", help="Show daemon status")
    sub.add_parser("stop", help="Stop a running daemon")

    args = parser.parse_args()

    if args.command == "run":
        if not args.config:
            parser.error("--config is required for 'run'")
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "stop":
        if not args.config:
            parser.error("--config is required for 'stop'")
        cmd_stop(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
