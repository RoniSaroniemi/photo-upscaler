---
name: verify
description: One-command self-verification — start app, health check, screenshot pages, run tests, analyze evidence, produce structured report.
---

# /verify

Run a self-verification pass on the current project: start the app, check health, screenshot pages, run tests, analyze evidence, and produce a structured report.

```
/verify [--url <base-url>] [--pages <page1,page2>] [--tests] [--output <dir>]
```

## When to Use

- After completing a brief or feature — verify the app actually works
- Before creating a PR — quick health check
- After deploying or merging — confirm nothing broke
- When you want a visual record of current app state

## Instructions

Follow these steps **in order**. Do not skip the analysis step — capturing screenshots without looking at them is pointless.

### Step 0: Setup

Parse arguments (all optional):
- `--url <base-url>` — base URL to verify (auto-detected if omitted)
- `--pages <page1,page2,...>` — comma-separated paths to screenshot (default: `/`)
- `--tests` — force running tests even if no test directory is auto-detected
- `--output <dir>` — output directory (default: `evidence/verify-<YYYYMMDD-HHMMSS>/`)

Create the output directory:
```bash
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="${OUTPUT:-evidence/verify-$TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"
```

### Step 1: Detect Project Type

Check what kind of project this is and determine the start command and default port:

| Signal | Type | Start Command | Default Port |
|--------|------|--------------|-------------|
| `package.json` with `"dev"` script | Next.js / Node | `npm run dev` | 3000 |
| `package.json` with `"start"` script | Node | `npm start` | 3000 |
| `requirements.txt` + `main.py` | Python (FastAPI/Flask) | `python3 main.py` | 8000 |
| `manage.py` | Django | `python3 manage.py runserver` | 8000 |
| `Cargo.toml` | Rust | `cargo run` | 8080 |
| `go.mod` | Go | `go run .` | 8080 |

If no web app is detected (e.g., this is a framework or library), skip to Step 4.

### Step 2: Start App & Health Check

First, check if something is already running on the target port:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT} 2>/dev/null
```

**If already responding:** Skip starting the app. Use the running instance.

**If not responding:** Start the app in the background:

```bash
# Start in background, capture PID for cleanup
${START_COMMAND} > "$OUTPUT_DIR/app-stdout.log" 2>&1 &
APP_PID=$!
```

Wait for it to respond (max 30 seconds):

```bash
for i in $(seq 1 30); do
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT} 2>/dev/null | grep -q "200\|301\|302\|304"; then
    echo "App responding after ${i}s"
    break
  fi
  sleep 1
done
```

Record the health check result:
- **Responds (2xx/3xx):** note the status code
- **No response after 30s:** note as "not responding" — continue with tests, skip screenshots
- **Error response (4xx/5xx):** note the error — still try screenshots (error pages are evidence)

### Step 3: Screenshot Pages

Use Playwright to capture each page. Default pages: just `/`. If `--pages` was given, screenshot those too.

For each page path:

```python
python3 << 'PYEOF'
import sys
from playwright.sync_api import sync_playwright

base_url = sys.argv[1]  # e.g., "http://localhost:3000"
page_path = sys.argv[2]  # e.g., "/" or "/upload"
output_path = sys.argv[3]  # e.g., "evidence/verify-.../homepage.png"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        page.goto(f"{base_url}{page_path}", timeout=20000)
        page.wait_for_load_state("networkidle", timeout=15000)
        page.screenshot(path=output_path, full_page=False)
        print(f"OK: {page_path} -> {output_path}")
    except Exception as e:
        print(f"FAIL: {page_path} -> {e}")
    finally:
        browser.close()
PYEOF
```

Name screenshots after the page path: `/` -> `homepage.png`, `/upload` -> `upload.png`, `/pricing` -> `pricing.png`.

### Step 4: Run Tests

Auto-detect and run the test suite. Check in this order:

1. **`package.json`** has `"test"` script (and it's not the default `echo "Error: no test specified"`) -> `npm test`
2. **`tests/` directory** exists with Python files -> `python3 -m pytest tests/ -v`
3. **`scripts/test-setup.sh`** exists -> `bash scripts/test-setup.sh`
4. **`scripts/test.sh`** exists -> `bash scripts/test.sh`

If `--tests` flag was passed, also look for less common patterns:
- `Makefile` with `test` target -> `make test`
- `cargo test` for Rust projects

Capture test output:
```bash
${TEST_COMMAND} > "$OUTPUT_DIR/test-output.txt" 2>&1
TEST_EXIT=$?
```

Record: command used, exit code, and output (truncated to last 100 lines if long).

### Step 5: Analyze the Evidence (CRITICAL)

**This is the most important step. Do not skip it.**

1. **Read each screenshot** you captured using the `Read` tool. For each one, assess:
   - Does the page render correctly? Is there actual content, or is it blank/error?
   - Is the layout intact? Any broken elements, overlapping text, missing images?
   - Does the UI match what the project is supposed to do?
   - Are there console errors visible or error messages on the page?

2. **Read the test output** (`$OUTPUT_DIR/test-output.txt`). Assess:
   - How many tests passed/failed?
   - What specifically failed and why?
   - Are failures related to the recent changes or pre-existing?

3. **Read the app logs** (`$OUTPUT_DIR/app-stdout.log`) if the app was started. Look for:
   - Startup errors or warnings
   - Runtime exceptions
   - Missing dependencies or configuration

4. **Form a judgment**: PASS, FAIL, or PARTIAL — with a clear reason.

### Step 6: Produce Report

Write the report to `$OUTPUT_DIR/report.md`:

```markdown
# Verification Report — <TIMESTAMP>

## Health Check
- URL: <base-url>
- Status: responds (CODE) / not responding / error (details)
- App started by verify: yes (PID) / no (already running) / no (not a web app)

## Screenshots
| Page | Screenshot | Status |
|------|-----------|--------|
| / | [homepage.png](homepage.png) | Captured / Failed (reason) |
| /upload | [upload.png](upload.png) | Captured / Failed (reason) |

## Tests
- Runner: <command used>
- Exit code: <0 or non-zero>
- Result: X passed, Y failed
- Output (last 50 lines):
```
<truncated test output>
```

## Visual Assessment
<For each screenshot you read, describe what you see. Be specific.>
- Homepage: <what does it show? correct layout? any issues?>
- /upload: <description>

## Issues Found
- <List any problems discovered, or "None" if everything looks good>

## Summary
<PASS|FAIL|PARTIAL> — <one-line assessment based on what you actually observed>
```

### Step 7: Cleanup

If you started the app in Step 2, stop it:
```bash
kill $APP_PID 2>/dev/null
```

Print the path to the report so the caller knows where to find it.

## Smart Defaults

With zero arguments (`/verify` alone), the skill:
- Auto-detects project type, start command, and port
- Defaults to screenshotting just `/`
- Auto-detects the test runner
- Outputs to `evidence/verify-<timestamp>/`
- If no web app is detected, skips health check and screenshots, runs only tests
- If no tests are detected and no web app, reports "nothing to verify" (still useful — it confirms the detection logic)

## What This Does NOT Do

- Does not fix issues — only reports them
- Does not block the agent — the report is informational
- Does not replace comprehensive E2E tests — it's a quick health check
- Does not require the app to be running — if it can't start, that's a finding

## Notes

- **Works in worktrees** — all paths are relative to the current working directory
- **Playwright required** — Chromium cached at `~/Library/Caches/ms-playwright/`. If Playwright is not installed, skip screenshots and note it in the report.
- **Timeout safety** — app startup waits max 30s. Playwright page loads timeout at 20s. Never hang forever.
- **Port conflicts** — if the detected port is busy, verify against whatever is running there. Don't try to kill existing processes.
- **Evidence is gitignored** — `evidence/` is in `.gitignore`. Reports are for the agent's and reviewer's benefit, not committed to the repo.
