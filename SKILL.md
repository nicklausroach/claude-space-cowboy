---
name: claude-space-cowboy
description: "Run coding jobs in fresh Ona environments: for each job, create an Ona environment in the right project, prepare it, add it to Herdr (terminal or desktop app) and run one or more claude-cowboy Claude Code agents there, each in its own Git worktree, then combine their work into one PR or a gh stack of PRs. Also drives agents on saved Herdr SSH machines. Use when the user invokes /claude-space-cowboy, asks for an agent or job \"in Ona\" / \"in a new environment\", or names a remote machine for cowboy agents. For agents in the current repo on this machine only, use claude-cowboy instead."
---

# claude-space-cowboy

Each job gets its own **Ona environment**. You create it, the helper prepares it
(Claude Code, claude-cowboy, Herdr core, gh + gh-stack, work git email) and adds it to
Herdr as a machine named `cowboy-<job>`. Then you run **claude-cowboy** agents in
it: each agent is a Claude Code session in its own worktree and branch, shown as a Herdr
tab. You review, steer and land their work from here.

Everything goes through one helper. Always call it by this literal path so the user's
permission allow-rule matches:
`~/.claude/skills/claude-space-cowboy/scripts/space-cowboy` (below: `space-cowboy`).

## Preconditions

- `ona whoami` works (else the user runs `! ona login`).
- This session runs inside Herdr: the desktop app (`HC_TERMINAL_ID` set) or the terminal
  app (`HERDR_ENV=1`). Environments show up in whichever one this is.

## If invoked with arguments

| Invocation | Do |
| --- | --- |
| (no args) | `space-cowboy env list` and `space-cowboy status`, summarize, offer next actions |
| `status` / `st` | `space-cowboy status` |
| `envs` | `space-cowboy env list` |
| `on <machine> <task…>` | Spawn one agent on that existing machine (no new environment) |
| anything else | A job: run the workflow below |

## Workflow

### 1. Pick the project, then confirm with the user

Find the Ona project that holds the repo: `space-cowboy env projects` lists them with the
path each repo gets inside an environment (`/workspaces/<repo>`). `env create` accepts a
project id, its name or its repo name (`dbt`, `analytics-cluster`, `obsidian`). If more
than one project fits, or none, ask.

**Before creating anything, tell the user in plain words and wait for a yes:** "I'll
create an Ona environment `cowboy-<job>` from project <Project> (region Ohio, auto-stops
after 4h disconnected), install Claude Code, claude-cowboy, Herdr core and the gh-stack
extension in it, set your work git email there, add it to Herdr, and stop it once its PRs
are open." One yes covers that environment, its setup and that stop. A new environment
needs a new yes.

### 2. Create the environment

```bash
space-cowboy env create <project> --name "<2-3 word job name>"
```

Takes a few minutes (Bash timeout 900000). It prints progress, the setup checklist and
finally the machine name and repo path. Options: `--region` (runner region, default Ohio),
`--class-id`, `--inactivity-timeout` (default 4h). Defaults can be set in config.json
(below).

- **"missing authentication token for github.com"**: Ona has no GitHub sign-in for the
  user on that region's runner. Use a region they're signed in on (`--region`), or ask them
  to create one environment in that region at app.gitpod.io to connect GitHub.
- **A `✗` in the checklist**: the environment exists and is recorded but isn't ready. Tell
  the user what failed. After a fix, `space-cowboy env setup <machine>` repeats the setup
  (safe to run again).

### 3. Plan: one agent or a stack

One focused change → one agent. A larger job → split it into layers that each make a
reviewable PR (under ~500 changed lines) and run one agent per layer **in the same
environment**: each gets its own worktree and branch off the same clone, so every branch is
visible to the others.

- Layers that build on each other: spawn layer N+1 with `--base <layer N's branch>` once
  layer N is done and reviewed.
- Independent layers can run at once off `main`; restack them in order when landing
  (`git rebase --onto <previous branch> main <branch>`, in a worktree).

### 4. Delegate

```bash
space-cowboy on cowboy-<job> spawn -t "add validation" --repo /workspaces/<repo> -f /tmp/prompt.md
# -f FILE is read on THIS machine and sent over; -p "…" and -p - work too.
# All claude-cowboy spawn options work: -a -m -e --harness --base --include-dirty
```

Write prompts the way claude-cowboy describes: goal, constraints, what done looks like.
Agents run with permission checks bypassed by default. Say so the first time you spawn in
an environment. Agent ids are per machine. Call them `cowboy-<job>:<id>` to the user and
send every command for an agent to its own machine.

### 5. Get notified

Right after each spawn, start one waiter per agent **with Bash `run_in_background: true`**:

```bash
space-cowboy on cowboy-<job> wait <id>
```

Don't poll. If SSH drops, the helper reconnects and waits again; agent state lives in the
environment. If a waiter still exits with an SSH error, start it again.

### 6. Review, steer, then report back

```bash
space-cowboy on cowboy-<job> diff <id> [--stat]
space-cowboy on cowboy-<job> steer <id> -m "follow-up instructions"   # then start a new waiter
space-cowboy on cowboy-<job> stop <id>
```

When the work looks good, report to the user (what changed, your verdict, branches), then
**stop and wait**.

### 7. Land the work (only when the user says so)

**Never push, open PRs, merge or clean up on your own.** Pushing is publishing: describe
what will be pushed and opened, and wait for a yes. Run git and gh in the environment over
SSH, using the target from `space-cowboy machines`:

```bash
ssh <target> 'cd <worktree> && git push -u origin <branch> && gh pr create --base main --head <branch> --title "…" --body "…"'
```

**A stack** (several layers): use `gh stack`, not hand-chained PR bases. From the top
layer's worktree (all branches are local there):

```bash
ssh <target> 'cd <top worktree> && gh stack init <b1> <b2> <b3> && gh stack submit --auto --open'
```

`--auto` titles the bottom PR from its branch name and fills bodies from the PR template;
fix them with `gh pr edit N --title … --body-file …`. To change a lower layer later: commit
on it, `gh stack rebase --no-trunk`, `gh stack push`.

After the PRs are open, **stop the environment** to save cost: `space-cowboy env stop
cowboy-<job>`. Its disk, branches, worktrees and agent reports are kept; agent processes
end. For review follow-ups, `space-cowboy env start cowboy-<job>` (about 20s; it prepares
itself again), then spawn a new agent with `--base <PR branch>` and tell it what to fix (a
stopped agent can't be steered back to life). Its commits land on a new branch on top of
the PR's. Once the user says to push, fast-forward the PR from the env:
`git push origin <agent branch>:<PR branch>`. For a lower stack layer, then run
`gh stack rebase --no-trunk` and `gh stack push`.

### 8. Clean up (only when the user says so)

```bash
space-cowboy on cowboy-<job> cleanup <id…>     # if the environment is running
space-cowboy env delete cowboy-<job>           # deletes the Ona environment and its Herdr machine
```

Deleting discards everything in the environment that wasn't pushed. Before it, check that
the branches are pushed (or tell the user which aren't) and get an explicit yes naming the
environment. `env delete` refuses while agents are still running (`--force` overrides; only
after the user confirms). It only deletes environments that `env create` made.

## Existing machines

Saved Herdr SSH machines (e.g. long-lived `*-primary` environments) still work with
`space-cowboy on <machine> …`, with the same steps 4 to 6 and no `env` commands.
`space-cowboy machines` lists every machine and its repos; `space-cowboy doctor [machine…]`
checks that agents can run there.

## Status

```bash
space-cowboy env list [--json]           # environments made here, with their Ona phase
space-cowboy status [machine…] [--json]  # agents on every machine, as machine:id
```

## Config (optional)

`~/.claude/claude-space-cowboy/config.json`:

```json
{
  "ona": { "region": "Ohio", "inactivity_timeout": "4h", "projects": { "ac": "Analytics Cluster" } },
  "machines": { "dbt-primary": { "repos": ["/workspaces/dbt"] } }
}
```

`ona.projects` adds short names for projects; `ona.git_email` / `ona.git_name` override
the git identity copied from this machine's global git config. Environments made here are
recorded in `envs.json` next to it.

## How an environment is prepared

`scripts/ona-bootstrap.sh` runs there and is safe to repeat. It installs Claude Code if
missing and marks the repos trusted. It skips the first-run and bypass-mode prompts. It
clones claude-cowboy, adds the gh-stack extension and sets the git identity. It writes
**no credentials**:

- Claude Code signs in from `CLAUDE_CODE_OAUTH_TOKEN`, which Ona mounts from the user's
  secrets. `claude auth status` says "not logged in" even then; agents still work.
- `gh` is a small wrapper in `~/.local/bin` that borrows git's Ona-provided GitHub
  credential on each call. A real `gh auth login` in the environment takes precedence.
- Worktrees start as plain checkouts (no copy-on-write there), without ignored files such
  as `node_modules` or virtualenvs.

## Rules for you, the coordinator

- Everything in claude-cowboy's "Rules for you, the orchestrator" applies.
- Confirm before each new environment (that yes also covers its setup and stopping it once
  its PRs are open), before every push or PR, before every deletion, and before any other
  stop or start.
- Send each command to the agent's own machine. Ids are only unique per machine.
- Reports and diffs come back into this session. If a task touches customer or other
  sensitive data, tell the agent to keep that data out of its report.
