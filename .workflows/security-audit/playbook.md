# Security Audit Playbook

**Type:** Horizontal agent — bounded workflow-triggered sup+exec pair
**Schedule:** Weekly (Monday 03:00 UTC)
**TTL:** 60 minutes (self-terminate on completion; watchdog kills if stalled)

---

## Instructions for Supervisor

You are running a bounded security audit. Follow these steps in order, record findings in the report, and terminate when done.

1. Create a report file at `.reports/security/YYYY-MM-DD.md` using the template at `.workflows/security-audit/report-template.md`
2. Run each of the 5 checks below
3. For each check, record PASS/FAIL in the report's Checks Performed table
4. For each finding, add a Findings entry with severity, file, issue, and recommendation
5. If critical findings exist: write a findings file to `<MAIN_REPO_PATH>/.cpo/findings/<run-id>-security.json` with priority `P1`, then notify via Telegram
6. If moderate findings exist: include them in the same findings file with priority `P2`
7. Low findings: document in report only (do not include in findings file)

> **Findings file protocol:** Get the main repo path with `python3 -c "import subprocess; print(subprocess.check_output(['git','worktree','list','--porcelain']).decode().split('\n')[0].replace('worktree ',''))"`. Write findings using the schema in `.cpo/findings/SCHEMA.md`. Use `source: "security-audit"`. **NEVER write directly to backlog.json** — the CPO integrates findings during 30-min checks.
8. Commit the report on the current branch
9. State "WORK COMPLETE — ready for merge"
10. **Kill your executor session and exit. Do not wait for further instructions.**

---

## Check 1: Secrets Scan

Scan tracked files for hardcoded API keys, tokens, passwords, and credentials.

**What to scan:**
- All `.py`, `.md`, `.json`, `.sh` files in the repo (excluding `.git/`)

**Patterns to flag:**
- Strings matching: `api_key`, `secret_key`, `access_token`, `password`, `credential`, `bearer`, `private_key`
- Base64-encoded strings longer than 40 characters that appear to be keys
- `.env` files committed to the repo

**Exclude (not findings):**
- Files in `.gitignore`
- Template/example files (e.g., `*.example`, placeholder values like `YOUR_API_KEY_HERE`)
- Documentation that describes credential handling without containing real credentials
- This playbook itself

**Severity:**
- Real credential found in tracked file → **critical**
- `.env` file committed → **critical**
- Suspicious but ambiguous pattern → **low**

---

## Check 2: Injection Vectors

Check for command injection vulnerabilities in subprocess and os.system calls.

**What to scan:**
- All `.py` files in `tools/`, `scripts/`, `.workflows/`

**Patterns to flag:**
- `subprocess.run()` or `subprocess.Popen()` with `shell=True` and f-string/format() arguments
- `os.system()` with any variable interpolation
- `subprocess.run()` with a string (not list) command that includes variable interpolation

**Safe patterns (not findings):**
- `subprocess.run()` with list arguments (no shell=True)
- `subprocess.run()` with hardcoded string commands
- `os.path.*` calls (not injection vectors)

**Severity:**
- `shell=True` with user-controlled input → **critical**
- `shell=True` with internally-controlled input → **moderate**
- `os.system()` with any interpolation → **moderate**

---

## Check 3: Permission Model

Verify agents run with appropriate permissions and dangerous flags are scoped correctly.

**What to check:**
- `--dangerously-skip-permissions` should only appear in agent tmux session launch commands (launch.py, delegate.py), not in user-facing scripts or documentation that instructs humans to use it
- `.claude/hooks/auto-approve-all.sh` — if present, verify it exists only in agent-context configurations
- `.claude/settings.json` — check that hook configurations are appropriate

**Severity:**
- Dangerous permissions in user-facing scripts → **critical**
- Overly permissive hooks in shared configs → **moderate**

---

## Check 4: Dependency Audit

Verify all Python tools use only the standard library (our design constraint).

**How to check:**
- For each `.py` file in `tools/`: parse imports with `ast` and verify all top-level modules are in `sys.stdlib_module_names`
- Alternatively: run the stdlib-only section of `scripts/test-setup.sh`

**Severity:**
- External dependency in core tool → **moderate**
- External dependency in optional/example script → **low**

---

## Check 5: File Permission Check

Verify executable scripts have appropriate filesystem permissions.

**What to check:**
- All `.sh` files should be executable (`chmod +x`)
- All `.py` files should NOT be executable (we invoke via `python3` explicitly)
- Check key scripts: `setup.sh`, `.claude/hooks/*.sh`, `tools/run_*.sh`, `.workflows/*/run.sh`

**Severity:**
- Non-executable `.sh` script → **low**
- Executable `.py` file → **low** (cosmetic, not a security risk)

---

## Notes

- All scan paths must be relative to the worktree root (this playbook may run in a worktree, not the main checkout)
- `test-setup.sh` has pre-existing known issues — note them in the report but do not report as new findings
- If no issues are found, record "clean" status in the report summary
