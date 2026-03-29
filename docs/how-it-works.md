# How It Works — A Beginner's Guide

This guide explains the Claude Orchestration Framework in plain terms. No AI experience required.

---

## The Big Idea

You have a project. You want AI agents to help you build it — not just answer questions, but actually do the work: write code, run tests, manage tasks, and keep things moving even when you step away.

This framework sets up a **team of AI agents** that work together, each with a clear role. You're the boss. They do the work.

```
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │    YOU (the human)                                  │
  │    "I want to build X"                              │
  │                                                     │
  │    You communicate via:                             │
  │    • Direct chat in the terminal                    │
  │    • Telegram messages (text or voice)              │
  │    • Or just walk away — the system keeps working   │
  │                                                     │
  └──────────────────────┬──────────────────────────────┘
                         │
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │    CPO (Chief Project Orchestrator)                  │
  │    Your right-hand AI. Always running.              │
  │                                                     │
  │    • Understands the big picture                    │
  │    • Breaks work into tasks                         │
  │    • Delegates to other agents                      │
  │    • Checks in every 30 minutes                     │
  │    • Sends you updates via Telegram                 │
  │    • Works through a backlog when you're away       │
  │                                                     │
  └───────┬────────────────────────┬────────────────────┘
          │                        │
          ▼                        ▼
  ┌───────────────┐      ┌───────────────────┐
  │   Director    │      │   Subconscious    │
  │  (temporary)  │      │    (background)   │
  │               │      │                   │
  │ Coordinates   │      │ Watches the CPO   │
  │ parallel work │      │ Detects if stuck  │
  │ Killed when   │      │ Nudges if idle    │
  │ done          │      │ Answers dialogs   │
  └───┬───────┬───┘      └───────────────────┘
      │       │
      ▼       ▼
  ┌───────┐ ┌───────┐
  │ Team1 │ │ Team2 │    Each team is:
  │       │ │       │
  │ Super │ │ Super │    Supervisor = plans & checks
  │ visor │ │ visor │    Executor   = does the work
  │   +   │ │   +   │
  │ Exec  │ │ Exec  │    Both are temporary —
  │ utor  │ │ utor  │    created for a task,
  │       │ │       │    killed when done.
  └───────┘ └───────┘
```

---

## The Roles Explained

### You (CEO)
You're the decision-maker. You:
- Say what you want built
- Approve big decisions
- Review results
- Set priorities

You don't need to manage the agents directly. The CPO handles that.

### CPO (always running)
Think of the CPO as a project manager that never sleeps. It:
- Reads your instructions and turns them into structured task descriptions ("briefs")
- Assigns work to teams of agents
- Monitors progress automatically (every 30 minutes)
- Reports back to you
- Works on improvements when there's nothing else to do

### Director (temporary)
When multiple things need to happen in parallel, the CPO spins up a Director. The Director:
- Manages 2+ teams at once
- Makes sure they don't conflict
- Merges completed work
- Gets destroyed when its work is done

### Supervisor + Executor (temporary teams)
Each task gets a two-agent team:
- **Supervisor** — plans the approach, checks quality, manages the process
- **Executor** — writes code, runs tests, produces results

This separation means the executor focuses on doing, while the supervisor focuses on checking.

### Subconscious (background watcher)
A lightweight agent that monitors the CPO from the background:
- Detects when the CPO is stuck or idle
- Navigates technical dialog boxes that would block the CPO
- Suggests what to work on next
- Knows whether you're at your computer (via ActivityWatch)

---

## What Happens When You Start a Project

```
  Step 1                Step 2               Step 3
  ──────                ──────               ──────
  You: "Build a         CPO writes a         CPO creates
  login system"    ──>  brief describing ──> Supervisor +
                        the task             Executor team

  Step 4                Step 5               Step 6
  ──────                ──────               ──────
  Executor builds       Supervisor checks    CPO merges the
  the code, runs   ──>  quality, verifies──> work, reports
  tests                 evidence             back to you
```

This cycle repeats for every task. Multiple tasks can run in parallel.

---

## How Decisions Work

Not every decision needs your input. The framework has four levels:

```
  ┌────────────────────────────────────────────────────────────┐
  │                                                            │
  │  Tier 1: CPO acts on its own                               │
  │  Bug fixes, small improvements, infrastructure             │
  │  "Just do it, tell me later"                               │
  │                                                            │
  ├────────────────────────────────────────────────────────────┤
  │                                                            │
  │  Tier 2: CPO proposes, you approve                         │
  │  New features, direction changes, big decisions            │
  │  "Here's my plan — should I proceed?"                      │
  │                                                            │
  ├────────────────────────────────────────────────────────────┤
  │                                                            │
  │  Tier 3: You decide, CPO advises                           │
  │  Releases, branding, strategy                              │
  │  "What do you think about X?"                              │
  │                                                            │
  └────────────────────────────────────────────────────────────┘
```

This means the CPO can fix bugs and improve tooling without waiting for you, but won't start a new major feature without your approval.

---

## Communication

You can talk to the CPO in two ways:

### 1. Direct chat (terminal)
Open the CPO's terminal and type. This is best for real-time collaboration.

### 2. Telegram (async)
The CPO has its own Telegram bot. You can:
- Send text messages
- Send voice notes (the CPO transcribes and reads them)
- Receive text or voice updates from the CPO
- Check in from your phone while away from the computer

```
  ┌──────────────┐         ┌──────────────┐
  │              │ text/   │              │
  │  Your phone  │ voice   │  CPO agent   │
  │  (Telegram)  │◄───────►│  (terminal)  │
  │              │         │              │
  └──────────────┘         └──────────────┘

  You can walk away. The CPO keeps working.
  When something needs your attention, it messages you.
```

---

## What's Running Where

Everything runs in **tmux** — a terminal multiplexer that keeps sessions alive even if you close your terminal window. Each project gets its own **tmux server** (via `-L <project-slug>`), so sessions from different projects are fully isolated — they can't see or affect each other, even if they share the same session names.

```
  Terminal windows (tmux sessions):
  ─────────────────────────────────

  [ cpo ]                Your CPO agent. Always running.
                         This is the "brain" of the operation.

  [ cpo-subconscious ]   Background watcher. Monitors the CPO.
                         You rarely need to look at this.

  [ sup-taskname ]       Supervisor for a specific task.
  [ exec-taskname ]      Executor for a specific task.
                         These come and go as tasks start/finish.

  [ telegram-pollers ]   Background process that delivers
                         Telegram messages to the right session.
```

You can peek at any session:
```bash
tmux -L $PROJECT_SLUG attach -t cpo              # Watch the CPO work
tmux -L $PROJECT_SLUG attach -t exec-taskname    # Watch an executor code
tmux -L $PROJECT_SLUG ls                         # List all active sessions
```

Detach without killing: press `Ctrl+B` then `D`.

---

## The 30-Minute Heartbeat

The CPO checks in automatically every 30 minutes. Each check:

```
  Every 30 minutes, the CPO asks itself:
  ──────────────────────────────────────

  1. Are any agents stuck?          → Unstick them
  2. Did any work finish?           → Review and merge it
  3. Any messages from the human?   → Read and respond
  4. Is the work queue empty?       → Start the next backlog item
  5. Is anything blocked on me?     → Unblock it
```

This means the system is self-healing. If an agent crashes, the next 30-minute check catches it and restarts things.

---

## Your Daily Workflow

A typical day looks like this:

```
  Morning:
  ────────
  • Check Telegram for overnight updates from CPO
  • Open terminal, attach to CPO session
  • Give new instructions or approve proposals
  • The CPO starts delegating work

  During the day:
  ───────────────
  • Work on other things
  • Get Telegram updates as tasks complete
  • Approve/reject proposals when they come in
  • Optionally watch agents work in real-time

  Evening:
  ────────
  • Tell the CPO what to work on overnight (or let it use the backlog)
  • Walk away — the CPO keeps working
  • The subconscious monitors everything
```

---

## Quick Reference

| Command | What it does |
|---------|-------------|
| `tmux -L $PROJECT_SLUG attach -t cpo` | Open the CPO's terminal |
| `tmux -L $PROJECT_SLUG ls` | List all running sessions |
| `Ctrl+B, D` | Detach from a tmux session (doesn't kill it) |
| `./setup.sh` | Run the initial project setup |
| `tmux -L $PROJECT_SLUG kill-session -t name` | Kill a specific session |

---

## FAQ

**Q: What if everything breaks?**
Kill all project sessions (`tmux -L $PROJECT_SLUG kill-server`), re-run `./setup.sh`, and start fresh. This only affects sessions in your project's tmux server — other projects are unaffected. All your project files are safe — only the agent sessions are ephemeral.

**Q: Do I need to keep my computer on?**
Yes — the agents run locally on your machine. If your computer sleeps, they pause. When it wakes, they resume on the next 30-minute check.

**Q: Can I have multiple projects?**
Yes. Clone the framework into each project directory. Each gets its own CPO, its own Telegram bot, and its own isolated tmux server (via the `tmux_server` config). Sessions from different projects never interfere with each other.

**Q: What if the CPO makes a mistake?**
The CPO works on branches, not directly on your main code. Nothing gets merged without verification. And Tier 2+ decisions always wait for your approval.

**Q: How much does this cost?**
The agents use your Claude API subscription (Claude Max or API credits). The framework itself is free. Telegram bots are free. All other tools are free and local.
