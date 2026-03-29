"""Reusable PID-file lock utility (stdlib-only).

Usage as library:
    from tools.pid_lock import PidLock

    with PidLock("/tmp/my.lock"):
        # exclusive section
        ...

Usage as CLI:
    python3 tools/pid_lock.py status <path>
    python3 tools/pid_lock.py release <path>
"""

import argparse
import os
import signal
import sys
import tempfile
from pathlib import Path


class PidLock:
    def __init__(self, lock_path: str):
        self.lock_path = Path(lock_path)
        self._locked = False
        self._prev_sigterm = None
        self._prev_sigint = None

    # -- public API ----------------------------------------------------------

    def acquire(self, blocking: bool = True) -> bool:
        """Try to acquire the lock.

        If *blocking* is True and the lock is held by a live process, return
        False (no busy-wait).  A stale lock (dead PID / unreadable) is cleaned
        up automatically.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        if self.lock_path.exists():
            owner = self._read_owner()
            if owner is not None and _pid_alive(owner):
                return False  # held by a live process
            # Stale or unreadable — remove and proceed.
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass

        self._write_pid()
        self._locked = True
        self._install_signal_handlers()
        return True

    def release(self) -> None:
        """Release the lock by removing the lock file."""
        if self._locked:
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass
            self._locked = False
            self._restore_signal_handlers()

    @staticmethod
    def is_locked(lock_path: str) -> bool:
        """Return True if *lock_path* exists and contains a live PID."""
        p = Path(lock_path)
        if not p.exists():
            return False
        try:
            pid = int(p.read_text().strip())
        except (ValueError, OSError):
            return False
        return _pid_alive(pid)

    # -- context manager -----------------------------------------------------

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(
                f"Could not acquire lock {self.lock_path} — held by another process"
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

    # -- internals -----------------------------------------------------------

    def _read_owner(self):
        """Return the PID written in the lock file, or None."""
        try:
            return int(self.lock_path.read_text().strip())
        except (ValueError, OSError):
            return None

    def _write_pid(self):
        """Atomically write the current PID to the lock file."""
        fd, tmp = tempfile.mkstemp(dir=self.lock_path.parent)
        closed = False
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            closed = True
            os.replace(tmp, self.lock_path)
        except BaseException:
            if not closed:
                os.close(fd)
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _signal_handler(self, signum, frame):
        """Release lock, then re-raise the original signal."""
        self.release()
        # Re-raise with the previous handler (default or user-installed).
        prev = self._prev_sigterm if signum == signal.SIGTERM else self._prev_sigint
        if callable(prev):
            prev(signum, frame)
        elif prev == signal.SIG_DFL:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

    def _install_signal_handlers(self):
        self._prev_sigterm = signal.getsignal(signal.SIGTERM)
        self._prev_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _restore_signal_handlers(self):
        if self._prev_sigterm is not None:
            signal.signal(signal.SIGTERM, self._prev_sigterm)
            self._prev_sigterm = None
        if self._prev_sigint is not None:
            signal.signal(signal.SIGINT, self._prev_sigint)
            self._prev_sigint = None


def _pid_alive(pid: int) -> bool:
    """Return True if a process with *pid* is currently running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but we can't signal it
    return True


# -- CLI ---------------------------------------------------------------------

def _cli():
    parser = argparse.ArgumentParser(
        description="PID lock file utility",
    )
    sub = parser.add_subparsers(dest="command")

    p_status = sub.add_parser("status", help="Check lock status")
    p_status.add_argument("path", help="Path to the lock file")

    p_release = sub.add_parser("release", help="Force-release a lock")
    p_release.add_argument("path", help="Path to the lock file")

    args = parser.parse_args()

    if args.command == "status":
        p = Path(args.path)
        if not p.exists():
            print(f"No lock file at {p}")
            sys.exit(0)
        try:
            pid = int(p.read_text().strip())
        except (ValueError, OSError) as e:
            print(f"Lock file exists but is unreadable: {e}")
            sys.exit(1)
        alive = _pid_alive(pid)
        state = "alive" if alive else "dead (stale lock)"
        print(f"Lock held by PID {pid} — process is {state}")

    elif args.command == "release":
        p = Path(args.path)
        if not p.exists():
            print(f"No lock file at {p}")
            sys.exit(0)
        try:
            p.unlink()
            print(f"Removed lock file {p}")
        except OSError as e:
            print(f"Failed to remove lock file: {e}")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _cli()
