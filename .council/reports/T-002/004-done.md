---
task: T-002
status: done
percent: 100
touched: []
needs: []
verify: ["grep -n 'marketplace add sitkowsp/super-claude-code' docs/social/posts.md (2 hits: Facebook, Instagram)", "grep -n 'github.com/sitkowsp' docs/social/posts.md (only line 9, the intro note)", "grep -n '\\`council\\`' docs/social/posts.md (only the H1 heading and Re-render section, not inside the Facebook/Instagram post bodies)", "manually confirm the hook/intro paragraph in the Facebook and Instagram bodies is a single unwrapped line each"]
dissent: false
---
Re-checked `docs/social/posts.md` after the rebase-conflict rejection noted in ANSWER.md. The
rebuilt workdir already contains the current base plus all previously approved content — no diff
was needed, so no file was touched this round.

Confirmed against the current README.md (rc9) and the task criteria:
- Both install lines (`/plugin marketplace add sitkowsp/super-claude-code` then
  `/plugin install council@super-claude-code`) appear as plain, unfenced lines in both the
  Facebook and Instagram sections, introduced by "Two lines inside Claude Code:".
- No GitHub URL inside either post body; the URL only appears once, in the intro note at the top
  (line 9). Both bodies end with a link-in-comment line ("Link to the repo is in the first
  comment." / "Link in the first comment.").
- Executor list and phrasing ("ChatGPT Codex, Google Antigravity, GitHub Copilot, Grok and a
  local Ollama") match README.md's current wording; plugin name `council`, marketplace
  `sitkowsp/super-claude-code`, and MIT license are all consistent.
- No backticks/markdown inside the Facebook or Instagram post bodies; each intro paragraph is a
  single physical line (not hard-wrapped).
- Facebook: hook line + description + 5 emoji bullets + install lines + MIT/link line + 15
  hashtags. Instagram: hook + short lines + 4 emoji bullets + install lines + link line + dot
  separator + 20 hashtags. X/Threads and Re-render sections left untouched.

Task complete; nothing left to do.
