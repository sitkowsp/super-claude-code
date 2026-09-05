---
task: T-002
status: done
percent: 100
touched: [docs/social/posts.md]
needs: []
verify: ["grep -n '/plugin marketplace add sitkowsp/super-claude-code' docs/social/posts.md (2 hits: Facebook, Instagram)", "grep -n 'github.com/sitkowsp' docs/social/posts.md (only in intro note, not inside Facebook/Instagram bodies)", "manually confirm Facebook body word count ~124 words (120-220), Instagram ~70 words (60-120), 15 hashtags on Facebook, 20 on Instagram"]
dissent: false
---
Rewrote Facebook and Instagram sections in `docs/social/posts.md` as final, copy-paste-ready
posts, no other files touched.

- Facebook (~124 words body): hook line, description matching README facts (plugin `council`,
  executors ChatGPT Codex / Google Antigravity / GitHub Copilot / Grok / local Ollama, isolated
  repo copy per branch), 5 emoji bullets (tokens, one branch per task, secrets, gates, Obsidian),
  the two install lines as plain text (no backticks/fences), then "MIT licensed, open source. Link
  to the repo is in the first comment." and 15 hashtags.
- Instagram (~70 words body): punchy lines, emoji, same two plain install lines, "Link in the
  first comment.", dots separator, 20 hashtags — the URL is not in either post body, only in the
  top intro note.
- X/Threads and Re-render sections left untouched (no typos found). Intro updated: "now show both
  install lines" referring to the graphics.
- All facts cross-checked against README.md: plugin name `council`, marketplace
  `sitkowsp/super-claude-code`, executor list, MIT license — no invented features.
