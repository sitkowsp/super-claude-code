# Social posts — `council` for Claude Code

Graphics in this folder (rendered from the `.html` files with headless Edge; edit the HTML and
re-render, see bottom) now show both install lines:

- `council-facebook-1200x630.png` — Facebook / LinkedIn / X link card
- `council-instagram-1080.png` — Instagram feed (square)

Repo link to drop in the first comment: https://github.com/sitkowsp/super-claude-code

---

## Facebook / LinkedIn

Claude Code now has a council. 🏛️

One repo, several AI subscriptions you already pay for — now working together instead of sitting in
separate windows. `council` is an open-source Claude Code plugin: Claude plans, delegates, reviews
and merges, while ChatGPT Codex, Google Antigravity, GitHub Copilot, Grok and a local Ollama execute
in parallel, each in an isolated copy of the repo, on its own git branch.

💸 Saves your Claude tokens — docs, assets and chores go to an executor
🌿 One git branch per task, reviewed and merged by Claude
🔒 Secrets never leave your machine
🚦 Gates run before every merge
📓 Plans and decisions land in Obsidian

Two lines inside Claude Code:

/plugin marketplace add sitkowsp/super-claude-code
/plugin install council@super-claude-code

MIT licensed, open source. Link to the repo is in the first comment. 👇

#ClaudeCode #Claude #Anthropic #Codex #ChatGPT #Antigravity #GitHubCopilot #Grok #Ollama #OpenSource #AIAgents #DeveloperTools #Automation #LLM #Obsidian

---

## Instagram

Claude Code now has a council. 🏛️

Claude plans, reviews and merges. ChatGPT Codex, Google Antigravity, GitHub Copilot, Grok and a
local Ollama do the work — in parallel, each in its own copy of your repo. 🧑‍💻⚡

✅ Saves your Claude tokens
🌿 One git branch per task
🔒 Secrets never leave your machine
📓 Plans and decisions land in Obsidian

Two lines inside Claude Code:

/plugin marketplace add sitkowsp/super-claude-code
/plugin install council@super-claude-code

Open source, MIT. Link in the first comment. 👇

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
