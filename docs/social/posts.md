# Social posts — `council` for Claude Code

Graphics in this folder (rendered from the `.html` files with headless Edge; edit the HTML and
re-render, see bottom):

- `council-facebook-1200x630.png` — Facebook / LinkedIn / X link card
- `council-instagram-1080.png` — Instagram feed (square)

Repo link to drop in the first comment: https://github.com/sitkowsp/super-claude-code

---

## Facebook / LinkedIn

**Claude Code now has a council. 🏛️**

One repo. Several AI subscriptions you already pay for. Until now they sat in separate windows.

`council` is an open-source Claude Code plugin that puts Claude in the chair and lets the others do
the work:

🟠 Claude Code — plans, delegates, reviews, merges
🟢 ChatGPT Codex — code, logos, PNG assets
🔵 Google Antigravity — code, images
🟣 GitHub Copilot — docs and copy
🟡 Grok + local Ollama — review and second opinions, free tokens

Every task runs in parallel, in its own isolated copy of your repo, on its own git branch. Executors
never see your secrets, never touch git, and everything they write is treated as data, not
instructions. Claude reviews the diff, runs your gates and merges.

Why? Because Claude's 5-hour window is the scarce resource. The plugin enforces a delegation policy:
docs, assets, chores and anything over ~40 lines go to an executor. When a model runs out of quota,
the task falls back automatically. When your window is about to end, `/council:offload` hands the
rest to the council and leaves a note for the next session.

Bonus: it mirrors plans, decisions and reports into Obsidian, so your vault becomes the project's
memory — and with the Claudian plugin, the vault talks back.

Install in two lines inside Claude Code:

/plugin marketplace add sitkowsp/super-claude-code
/plugin install council@super-claude-code

MIT licensed. Link in the first comment. 👇

#ClaudeCode #Claude #Anthropic #Codex #ChatGPT #Antigravity #GitHubCopilot #Grok #Ollama #OpenSource #AIAgents #DeveloperTools #Automation #LLM #Obsidian

---

## Instagram

**Claude Code now has a council. 🏛️**

Claude plans, reviews and merges.
ChatGPT Codex, Google Antigravity, GitHub Copilot, Grok and a local Ollama do the work — in parallel, each in its own copy of your repo. 🧑‍💻⚡

✅ Saves your Claude tokens
🌿 One git branch per task
🔒 Secrets never leave your machine
📓 Plans and decisions land in Obsidian

Open source, MIT. Two lines to install inside Claude Code. Link in bio / first comment. 👇

.
.
.
#ClaudeCode #Claude #Anthropic #ChatGPT #Codex #Antigravity #GoogleAI #GitHubCopilot #Grok #Ollama #OpenSource #AIAgents #DevTools #Programming #Coding #SoftwareEngineering #Automation #LLM #Obsidian #BuildInPublic

---

## X / Threads (short)

Claude Code now has a council 🏛️ — Claude plans, reviews & merges while ChatGPT Codex, Google
Antigravity, GitHub Copilot, Grok and a local Ollama execute in parallel, each in an isolated copy of
your repo. Saves your Claude tokens. Open source. 👇

#ClaudeCode #Codex #Antigravity #Copilot #Ollama #OpenSource

---

## Re-render the graphics (Windows, Edge)

```powershell
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$d = (Resolve-Path docs\social).Path
& $edge --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$env:TEMP\edge-prof" --window-size=1200,630  --screenshot="$d\council-facebook-1200x630.png" "file:///$($d -replace '\\','/')/graphic-wide.html"
& $edge --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$env:TEMP\edge-prof" --window-size=1080,1080 --screenshot="$d\council-instagram-1080.png" "file:///$($d -replace '\\','/')/graphic-square.html"
```

Any Chromium browser works the same way (`chrome --headless=new --screenshot=…`).
