

# AGENT SETUP — Self-Configuration for Aletheia

**You are an AI agent reading this file as your first action on the Aletheia project.** Your job right now is to make sure you have every capability required to work autonomously, then continue from the project state.

Do not ask the user to read this file. Do not summarize it back to them. Read it, act on it, and report only what you need from them.

---

## §1 — Self-assessment: do you have what you need?

Before touching the project, verify you have all five capabilities. Run the checks below and note which pass and which fail.

| # | Capability | Check command |
|---|---|---|
| 1 | Filesystem read/write | `ls app/aletheia/adapters/` and `cat HANDOFF.md \| head -5` |
| 2 | Shell execution | `python --version && git --version` |
| 3 | GitHub auth | `gh auth status` |
| 4 | Docker access | `docker info` |
| 5 | Persistent workspace | `git log -1 --format="%H %s"` |

Run them. Note the results.

**If all five pass:** skip to §6 (start working).

**If one or more fail:** continue to §2 to self-configure what you can, and to §5 to request what you can't.

---

## §2 — What you can configure yourself

You have shell access (or you don't, in which case §5 applies). If you do, you can install and configure the following without human help.

### 2.1 Install missing CLI tools

**Windows:**
```bash
winget install --id GitHub.cli
winget install --id Git.Git
winget install --id Python.Python.3.13
```

**macOS:**
```bash
brew install gh git python@3.13
```

**Linux (Debian/Ubuntu):**
```bash
# gh CLI
type -p curl >/dev/null || sudo apt install curl -y
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh git python3.13 python3.13-venv -y
```

After installing, close and reopen your shell (or `source ~/.bashrc` / `refresh`) so PATH updates take effect.

### 2.2 Authenticate `gh` if a PAT is available

Check if a GitHub token exists in any of these locations, in order:

1. Environment variable `GH_TOKEN` or `GITHUB_TOKEN`
2. File `~/.aletheia_github_token` (or `%USERPROFILE%\.aletheia_github_token`)
3. `gh auth status` already returns success

If a token is found:

```bash
# From env
if [ -n "$GH_TOKEN" ]; then
  echo "$GH_TOKEN" | gh auth login --with-token
fi

# From file
TOKEN_FILE="$HOME/.aletheia_github_token"
[ -f "$TOKEN_FILE" ] && cat "$TOKEN_FILE" | gh auth login --with-token

gh auth status
```

If none is found, note it and continue to §5.

### 2.3 Verify Docker

If `docker info` fails:

- **Check if Docker is installed:** `command -v docker`
- **If not installed:** you cannot install Docker Desktop autonomously — it requires a GUI installer and admin privileges. Note this and continue to §5.
- **If installed but not running:** try to start it. On macOS: `open -a Docker`. On Windows: `Start-Process "Docker Desktop.exe"`. On Linux: `sudo systemctl start docker`.
- **If running but permission denied:** on Linux, `sudo usermod -aG docker $USER` then request a logout/login.

### 2.4 Verify the working directory

Ensure you are in the repo root:

```bash
cd /path/to/aletheia  # adjust for your environment
pwd
git status
```

The output of `pwd` should end in `aletheia`. The `git status` output should show a branch named `main`.

### 2.5 Set up the local Python environment (if you'll run tests locally)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -e '.[dev]'
pytest -q
```

If pytest passes, you can run tests locally. If it fails on import errors, note it — the CI has a working install; local setup is optional.

---

## §3 — What you cannot configure yourself

These require human action. Do not attempt to work around them; do not fabricate having them.

### 3.1 Docker installation

You cannot install Docker Desktop or Docker Engine without admin/root privileges and, on Windows/macOS, a GUI installer. If Docker is missing, request it from the user (see §5).

### 3.2 MCP server installation (if you're an MCP-based agent)

If you are a Claude Desktop-style agent that requires MCP servers for filesystem/shell access, you **cannot** install those servers into your own runtime — MCP servers are loaded at agent startup from a config file the human controls. If you discover you need MCP servers that aren't loaded, request them from the user (see §5).

**How to tell if you need MCP servers:** if the filesystem or shell checks in §1 fail, and you are not a CLI agent with native shell access, then you likely need MCP servers.

### 3.3 GitHub PAT creation

You cannot create a GitHub Personal Access Token. If `gh auth status` fails and no token is available via env or file, request one from the user (see §5).

### 3.4 System-level environment changes

You cannot add yourself to the `docker` group, enable WSL integration, or reboot the machine. If any of these are needed, request them from the user.

---

## §4 — Verification (run this before starting work)

Once §2 is done and §5 requests are resolved, verify:

```bash
pwd                                  # should end in aletheia
git log -1 --format="%H %s"          # should show the last commit
git status                           # should show branch main
gh auth status                       # should show logged in
docker info                          # should succeed
python --version                     # should be 3.12+
pytest -q --collect-only 2>&1 | tail -3  # should collect tests
```

If all succeed, proceed to §6.

If any fail, note which and re-request from the user (§5).

---

## §5 — What to request from the user

If any capability is missing and you cannot self-configure it, **stop and request it explicitly**. Do not proceed until the request is resolved. Do not fabricate.

Use this exact format:

```
SETUP BLOCKED — <capability>

What's missing: <one sentence>
Why I can't self-configure it: <one sentence>
What I need you to do: <numbered steps, exact commands or clicks>
How to verify it worked: <one command I'll run after>
```

**Examples of valid requests:**

```
SETUP BLOCKED — Docker

What's missing: Docker is not installed on this machine.
Why I can't self-configure it: Docker requires a GUI installer and admin privileges.
What I need you to do:
  1. Download Docker Desktop from https://www.docker.com/products/docker-desktop/
  2. Install it, start it, wait for the whale icon to be steady in the system tray
  3. Reopen this session
How to verify it worked: I'll run `docker info` after you confirm.
```

```
SETUP BLOCKED — GitHub authentication

What's missing: `gh auth status` fails and no GH_TOKEN or ~/.aletheia_github_token exists.
Why I can't self-configure it: I cannot create GitHub tokens.
What I need you to do:
  1. Go to github.com → Settings → Developer settings → Personal access tokens → Fine-grained
  2. Generate a token named "aletheia-agent" with these scopes: Actions:Read, Contents:Read+write, Workflows:Read+write, Metadata:Read, Pull requests:Read+write
  3. Save it to ~/.aletheia_github_token (or %USERPROFILE%\.aletheia_github_token on Windows)
  4. Confirm it's in .gitignore: `git check-ignore ~/.aletheia_github_token`
How to verify it worked: I'll run `gh auth status` after you confirm.
```

```
SETUP BLOCKED — MCP servers not loaded

What's missing: I don't have filesystem or shell access.
Why I can't self-configure it: MCP servers load at startup from a config file I cannot edit from inside a session.
What I need you to do:
  1. Open the MCP config file (Claude Desktop Windows: %APPDATA%\Claude\claude_desktop_config.json)
  2. Add the filesystem, shell, and docker servers — see docs/AGENT_SETUP.md §7 for the exact JSON
  3. Restart the agent completely
How to verify it worked: On restart, I'll run `ls app/aletheia/adapters/` and it should succeed.
```

**Do not bundle requests.** One gate per message. This keeps the human's action focused.

---

## §6 — After setup: start working

Once §4 passes, read the project state files in this order:

1. `docs/AUTONOMOUS_DIRECTIVE.md` — standing rules, execution order, handoff protocol
2. `HANDOFF.md` — current state, last verified commit, next action
3. `RESUME_STATE.json` — machine-readable resume point
4. `GATES.md` — open and resolved gates
5. `CHANGELOG.md` — recent changes
6. `docs/PROJECT_DIRECTION.md` — strategy and tier system
7. `docs/PHASE_5B_REGISTRY.md`, `docs/PHASE_5C_REGISTRY.md`, `docs/NOT_INTEGRATED.md` — adapter state

Then report the current state to the user in the format defined in `AUTONOMOUS_DIRECTIVE.md` §15:

```
PHASE <n> — <name>
Status: <complete | partial | blocked>
Commits: <list>
CI runs: <list>
What changed: <bullet list>
Open gates: <list or "none">
Next phase: <name>
```

Then continue from `RESUME_STATE.json.next_action`.

**Do not wait for confirmation** unless you hit a hard gate (see `AUTONOMOUS_DIRECTIVE.md` §13). Continue autonomously.

---

## §7 — MCP configuration (for agents that need it)

If you are an MCP-based agent and §1 filesystem/shell checks failed, this is the configuration the user needs to add to the agent's MCP config file. Give them this exact JSON block and the path for their agent.

**Claude Desktop (Windows):** `%APPDATA%\Claude\claude_desktop_config.json`
**Claude Desktop (macOS):** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Continue:** `~/.continue/config.json`
**Cline (VS Code):** managed via VS Code settings UI

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/absolute/path/to/aletheia"
      ]
    },
    "shell": {
      "command": "uvx",
      "args": ["mcp-shell-server"],
      "env": {
        "ALLOW_COMMANDS": "git,gh,python,pip,pytest,docker,bash,cat,ls,find,grep,echo,mkdir,cp,mv,rm,curl,tar,unzip,sha256sum,chmod,touch,head,tail,wc,sort,uniq,awk,sed"
      }
    },
    "docker": {
      "command": "uvx",
      "args": ["mcp-server-docker"]
    },
    "github": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
        "-e", "GITHUB_TOOLSETS=repos,issues,pull_requests,code_security",
        "ghcr.io/github/github-mcp-server"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "<YOUR_GITHUB_PAT>"
      }
    }
  }
}
```

**Tell the user to:**
1. Replace `/absolute/path/to/aletheia` with the actual absolute path to the repo
2. Replace `<YOUR_GITHUB_PAT>` with their token
3. Restart the agent completely
4. Verify by asking you to run `ls app/aletheia/adapters/` — if it succeeds, MCP loaded

If `uvx` is missing, the user also needs: `pip install uv`

---

## §8 — Capability class reference

Not every agent is the same. Identify your class to know what setup applies:

**Class A — Native capability agent.**
Examples: Codex CLI, Claude Code CLI, Aider, Cursor, Cline.
You have built-in filesystem and shell access. You do not need MCP servers. Only check §1 and install missing CLI tools via §2.

**Class B — MCP-based agent.**
Examples: Claude Desktop, some Continue and Zed configurations.
You need MCP servers loaded for filesystem, shell, Docker access. See §3.2 and §7.

**Class C — Sandboxed cloud agent.**
Examples: some cloud Codex variants, Replit Agent, GitHub Codespaces with AI.
You have filesystem and shell but may lack Docker or GitHub credentials. Check §1; if Docker is missing, you can still work by triggering GitHub Actions instead of local Docker.

**Class D — Chat-only agent.**
Examples: ChatGPT web, Claude web (non-Desktop), Gemini web.
You cannot work on Aletheia autonomously. Read this file, report to the user that you are Class D, and stop. Do not pretend to do work you cannot do.

**To self-identify:**
- If `ls` and `git` work but `docker info` fails and you're not in a sandbox: Class A with missing Docker.
- If `ls` fails entirely: Class B with no MCP loaded.
- If `ls` works and `git` works but no CI access: Class C.
- If you cannot run any command at all: Class D.

---

## §9 — Security rules for self-configuration

- **Never commit the GitHub PAT.** Verify `.gitignore` contains `.aletheia_github_token`, `*.token`, `.env.local` before doing anything with credentials.
- **Never echo the token.** Do not print it in logs, output, or commit messages.
- **Never install untrusted software.** Only install the tools listed in §2.1 and the MCP packages listed in §7. Do not install random `npm` or `pip` packages that claim to be "helper" or "utility" tools.
- **Never modify system files** (`.bashrc`, `/etc/hosts`, systemd units) unless the user explicitly approves.
- **Never run `rm -rf` on directories outside the repo.** The shell allowlist includes `rm` for legitimate cleanup; use it carefully.
- **If you detect a leaked token** (found in a committed file, in chat history, in shell history), tell the user immediately and instruct them to revoke it at github.com/settings/tokens.

---

## §10 — What to report after setup

Once §4 passes and you've read §6's files, report this exact format to the user:

```
AGENT READY

Capability class: <A | B | C>
Filesystem: <ok | missing>
Shell: <ok | missing>
GitHub auth: <ok as USERNAME | missing>
Docker: <ok | missing>
Working directory: <path>

Current project state:
<phase report from AUTONOMOUS_DIRECTIVE.md §15>

Open gates:
<list or "none">

Starting work on next_action:
<the exact next step>

No further action required from you unless a gate blocks.
```

After that, proceed autonomously.

---

## §11 — If you cannot get to a ready state

If after §2 and §5 you still cannot pass §4, do not attempt the project. Report:

```
AGENT NOT READY

Missing capabilities: <list>
What I attempted: <list>
Why it failed: <one paragraph>
What I need from the user: <specific, one item at a time>
```

Then wait. Do not proceed. Do not fabricate progress.

---

## §12 — Summary

1. Read this file.
2. Run the §1 checks.
3. Self-configure what §2 permits.
4. Request what §3 forbids you from doing yourself (using §5's format).
5. Verify with §4.
6. Read the project state files (§6).
7. Report readiness (§10).
8. Continue from `RESUME_STATE.json.next_action`.

No further briefing needed. The project state files plus this setup guide carry everything.

Go.

