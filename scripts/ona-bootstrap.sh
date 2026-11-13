#!/bin/sh
# claude-space-cowboy: prepare a fresh Ona environment to run claude-cowboy agents.
# Run inside the environment (space-cowboy pipes it over SSH). Safe to re-run.
#
# Inputs (environment variables):
#   COWBOY_REPOS        space-separated repo paths in the env to mark trusted for Claude Code
#   COWBOY_GIT_EMAIL    git user.email for agent commits (the coordinator's work email)
#   COWBOY_GIT_NAME     git user.name
#
# Never writes a credential. Claude Code signs in from CLAUDE_CODE_OAUTH_TOKEN, which Ona
# mounts from the user's secrets; gh borrows git's Ona-provided GitHub credential per call.
# Prints one "ok|warn|fail<TAB>step<TAB>detail" line per step.
set -u
say() { printf '%s\t%s\t%s\n' "$1" "$2" "$3"; }
bin="$HOME/.local/bin"
mkdir -p "$bin" "$HOME/.claude/skills"
case ":$PATH:" in *":$bin:"*) ;; *) PATH="$bin:$PATH" ;; esac

# 1. Claude Code
if command -v claude >/dev/null 2>&1; then
  say ok claude "$(claude --version 2>/dev/null | head -1)"
elif curl -fsSL https://claude.ai/install.sh | bash >/tmp/cowboy-claude-install.log 2>&1 && command -v claude >/dev/null 2>&1; then
  say ok claude "installed $(claude --version 2>/dev/null | head -1)"
else
  say fail claude "install failed; see /tmp/cowboy-claude-install.log"
fi
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then say ok claude-auth "CLAUDE_CODE_OAUTH_TOKEN is set (from Ona secrets)"
else say fail claude-auth "CLAUDE_CODE_OAUTH_TOKEN is not set; add it as an Ona user secret"; fi

# 2. Skip Claude Code's first-run, folder-trust and bypass-mode prompts (no secrets here).
python3 - "${COWBOY_REPOS:-}" <<'PY' && say ok claude-config "onboarding done, repos trusted" || say fail claude-config "could not update ~/.claude.json / settings.json"
import json, os, sys
home = os.path.expanduser("~")
def update(path, fn):
    try:
        data = json.load(open(path))
    except (OSError, ValueError):
        data = {}
    fn(data)
    tmp = path + ".cowboy-tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
def main_cfg(c):
    c["hasCompletedOnboarding"] = True
    for repo in sys.argv[1].split():
        c.setdefault("projects", {}).setdefault(os.path.realpath(repo), {})["hasTrustDialogAccepted"] = True
def settings(s):
    s["skipDangerousModePermissionPrompt"] = True
    allow = s.setdefault("permissions", {}).setdefault("allow", [])
    rule = "Bash(~/.claude/skills/claude-cowboy/scripts/cowboy:*)"
    if rule not in allow:
        allow.append(rule)
update(os.path.join(home, ".claude.json"), main_cfg)
os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
update(os.path.join(home, ".claude", "settings.json"), settings)
PY

# 3. claude-cowboy
cb="$HOME/.claude/skills/claude-cowboy"
if [ -d "$cb/.git" ]; then
  git -C "$cb" pull -q --ff-only 2>/dev/null; say ok claude-cowboy "$(git -C "$cb" log --oneline -1)"
elif git clone -q https://github.com/nicklausroach/claude-cowboy "$cb" 2>/tmp/cowboy-clone.log; then
  say ok claude-cowboy "cloned $(git -C "$cb" log --oneline -1)"
else
  say fail claude-cowboy "clone failed; see /tmp/cowboy-clone.log"
fi
# Herdr core starts agents with its own environment (no login PATH or Ona secrets) unless
# claude-cowboy launches them through a login shell.
if [ -f "$cb/scripts/cowboy" ] && ! grep -q 'def login_shell' "$cb/scripts/cowboy"; then
  say fail claude-cowboy "too old: agents would start without the login PATH and Ona secrets; update it"
fi

# 4. gh: a wrapper that hands gh the GitHub credential Ona gives git, looked up on each call.
real_gh=$(PATH=$(printf %s "$PATH" | tr ':' '\n' | grep -vx "$bin" | paste -sd: -) command -v gh 2>/dev/null)
if [ -z "$real_gh" ]; then
  say fail gh "gh is not installed in this env"
else
  cat >"$bin/gh" <<EOF
#!/bin/sh
# Written by claude-space-cowboy. Looks up git's Ona-provided GitHub credential for each
# gh call instead of storing a token; a real \`gh auth login\` takes precedence.
if [ -z "\${GH_TOKEN:-}\${GITHUB_TOKEN:-}" ] && [ ! -s "\$HOME/.config/gh/hosts.yml" ]; then
  GH_TOKEN=\$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | sed -n 's/^password=//p')
  export GH_TOKEN
fi
exec $real_gh "\$@"
EOF
  chmod +x "$bin/gh"
  if login=$("$bin/gh" api user -q .login 2>/dev/null); then say ok gh "signed in as $login (via git credential)"
  else say fail gh "gh cannot reach GitHub with git's credential"; fi
  if "$bin/gh" extension list 2>/dev/null | grep -q gh-stack; then say ok gh-stack "installed"
  elif "$bin/gh" extension install github/gh-stack >/dev/null 2>&1; then say ok gh-stack "installed $("$bin/gh" extension list | awk '/gh-stack/{print $NF}')"
  else say fail gh-stack "gh extension install github/gh-stack failed"; fi
fi

# 5. git identity for agent commits
if [ -n "${COWBOY_GIT_EMAIL:-}" ]; then
  git config --global user.email "$COWBOY_GIT_EMAIL"
  [ -n "${COWBOY_GIT_NAME:-}" ] && git config --global user.name "$COWBOY_GIT_NAME"
fi
say ok git-identity "$(git config user.name) <$(git config user.email)>"
