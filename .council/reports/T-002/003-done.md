---
task: T-002
status: done
percent: 100
touched: [docs/social/posts.md]
needs: []
verify: ["grep -n '/plugin marketplace add sitkowsp/super-claude-code' docs/social/posts.md (2 hits: Facebook, Instagram)", "grep -n 'github.com/sitkowsp' docs/social/posts.md (only in intro note, not inside Facebook/Instagram bodies)", "grep -n '\\`council\\`' docs/social/posts.md (should NOT match inside the Facebook body paragraph)", "manually confirm each paragraph in the Facebook and Instagram bodies is a single unwrapped line (no mid-sentence newlines)"]
dissent: false
---
Addressed both review rejections in `docs/social/posts.md`, no other files touched.

1. Un-wrapped the hard-wrapped paragraphs inside the Facebook and Instagram post bodies (the
   intro/hook paragraph in each) so each is now a single physical line, regardless of length —
   only bullets, the two install lines, the closing line and hashtags remain separate lines, as
   required for literal copy-paste onto Facebook/Instagram.
2. Removed the backticks around `council` inside the Facebook body paragraph (plain text now:
   "...council is an open-source Claude Code plugin..."). Markdown (backticks) is only kept in the
   intro note and the Re-render section, which are not pasted onto social platforms.

Everything else from the prior approved raport is unchanged: facts match README.md (plugin
`council`, marketplace `sitkowsp/super-claude-code`, executor list ChatGPT Codex / Google
Antigravity / GitHub Copilot / Grok / local Ollama, MIT license), install-line order, no GitHub
URL inside either post body, link-in-first-comment closing line on both, hashtag counts (15 on
Facebook, 20 on Instagram), and the X/Threads and Re-render sections left as-is.
