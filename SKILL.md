---
name: claude-space-cowboy
description: "Multi-machine coordinator for claude-cowboy: from one Claude Code session, spawn, steer, review and land background coding agents on several machines (this one plus SSH machines saved in Herdr), with each agent running in a Herdr workspace and Git worktree on the machine that holds its repo. Use when the user invokes /claude-space-cowboy, names a remote machine for cowboy agents (e.g. \"on devbox\"), or asks to run agents across machines. For agents in the current repo on this machine only, use claude-cowboy instead. Requires claude-cowboy on every machine and Herdr here."
---

# claude-space-cowboy

You coordinate **claude-cowboy** agents on several machines. Each agent runs on the
machine that holds its repo: its worktree, branch, Herdr workspace and state all live
there. You drive them from here with one helper,
`~/.claude/skills/claude-space-cowboy/scripts/space-cowboy`. Always call it by that literal
path so the user's permission allow-rule matches.

`space-cowboy on <machine> <cowboy command…>` runs a claude-cowboy command on that
machine, directly for `local` and over SSH for saved Herdr machines. Every claude-cowboy
command and flag works the same way, so follow the claude-cowboy workflow (delegate, get
notified, review and steer, land, clean up) and add `on <machine>` in front.

## Preconditions

Check these first. If one fails, tell the user and stop.

```bash
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy machines
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy doctor
```

- `machines` lists `local` plus every enabled Herdr SSH machine (`herdr machine add` adds
  more) and any repos configured for each.
- `doctor` checks each machine for claude-cowboy (a version with coordinator support),
  Python 3.11+, a running Herdr server, `git`, `claude` and copy-on-write cloning. A `✗`
  on a machine means agents can't run there yet. Copy-on-write is only a warning:
  worktrees then start without ignored files like `node_modules`.
- Spawning on `local` also needs this session to be inside a Herdr pane (`HERDR_ENV=1`).

## If invoked with arguments

| Invocation | Do |
| --- | --- |
| (no args) | `space-cowboy status`, then summarize and offer the next actions |
| `status` / `st` | `space-cowboy status` |
| `machines` | `space-cowboy machines` |
| `doctor [machine…]` | `space-cowboy doctor [machine…]` |
| `on <machine> <task…>` | Spawn one agent on that machine for the task |
| anything else | Treat it as a job to break down and delegate across machines |

## Workflow

### 1. Pick the machine and repo

Each subtask runs where its repo lives. Use the repos listed by `machines`, or what the
user tells you. If it's unclear which machine or path holds a repo, ask; don't guess.
Repos the user names can be saved for next time in
`~/.claude/claude-space-cowboy/config.json`:

```json
{ "machines": { "devbox": { "repos": ["~/api"] } } }
```

Paths are on that machine. `~` means the remote user's home.

### 2. Delegate

Same as claude-cowboy spawn, with `on <machine>` and `--repo <path on that machine>`:

```bash
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy on devbox spawn -t "fix validation" --repo ~/api -f /tmp/prompt.md
# -f FILE reads a prompt file on THIS machine and sends it over; -p "…" and -p - work too.
# All claude-cowboy spawn options work: -a -m -e --harness --base --include-dirty
```

The agent id that comes back belongs to that machine. Refer to agents as
`<machine>:<id>` (e.g. `devbox:k3x9q2ab`) when talking to the user, and always send
an agent's commands to its own machine. Concurrency limits apply per machine.

### 3. Get notified

Right after each spawn, start one waiter per agent **with Bash `run_in_background: true`**:

```bash
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy on devbox wait <id>
```

As in claude-cowboy, every spawned agent needs a waiter (queued ones too), and you don't
poll. If SSH drops, the helper reconnects and waits again a few times; agent state lives on
the machine, so nothing is lost. If a waiter still exits with an SSH error, start it again.

### 4. Review, steer, then report back

```bash
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy on devbox diff <id>          # commits + uncommitted changes
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy on devbox diff <id> --stat
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy on devbox steer <id> -m "follow-up instructions"
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy on devbox stop <id>
```

After a steer, start a new background waiter. When the work looks good, report to the
user (machine, what changed, your review verdict, branch and worktree path), then **stop
and wait**.

### 5. Land the work (only when the user says so)

**Never merge, push, open a PR or clean up on your own initiative.** The user decides how
work lands.

- **Pull request.** Push and open the PR on the agent's machine, from its worktree (paths
  come from `status --json` or the waiter output). Use the machine's SSH target from
  `machines`:
  ```bash
  ssh <target> 'cd <worktree> && git push -u origin <branch> && gh pr create --base <base> --head <branch> --title "…" --body "…"'
  ```
  On `local`, run the same commands without `ssh`.
- **Local merge** into that machine's main checkout:
  `space-cowboy on <machine> merge <id> [--target main]`

### 6. Clean up (only when the user says so)

`space-cowboy on <machine> cleanup <id>`. As in claude-cowboy, `--force` and
`--delete-unmerged` discard work, so use them only after the user explicitly confirms,
naming what will be lost.

## Status

```bash
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy status              # every machine
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy status devbox  # one machine
~/.claude/skills/claude-space-cowboy/scripts/space-cowboy status --json       # {machine: [agents] | {error}}
```

A machine that can't be reached shows as an error row. Its agents keep running.

## Rules for you, the coordinator

- Everything in claude-cowboy's "Rules for you, the orchestrator" applies here too.
- Send each command to the agent's own machine. Ids are only unique per machine.
- Configuration (`on <machine> config --set …`), templates and concurrency limits are per
  machine. Change another machine's config only when the user asks.
- Agents run with permission checks bypassed by default. Mention this the first time you
  spawn on each machine, especially remote ones that may have broader access than this one.
- Reports and diffs from remote machines come back into this session. If an agent's
  task touches customer or other sensitive data, tell it to keep that data out of its
  report.
