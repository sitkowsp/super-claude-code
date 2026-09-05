# Research: non-interactive raster image generation from Codex CLI, Gemini CLI, Copilot CLI

Date checked: 2026-09-05. Scope: can each CLI produce a PNG/JPG headlessly and land it in the
current working directory, and does that work on a subscription login (ChatGPT Plus/Pro, Google
account) rather than a pay-per-use API key. Nothing was installed or executed; all findings come
from official docs, the upstream repos and issue trackers, and community wrappers.

Versions referenced by the caller: `@openai/codex` 0.153, `@google/gemini-cli` 0.58,
`@github/copilot` (Copilot CLI) 1.0.x.

---

## 1. OpenAI Codex CLI (`codex`)

**Capability: YES (built-in), with reliability caveats.**

### Mechanism

- Codex ships a hosted **`image_gen` tool** (feature key `image_generation`). It was promoted from
  under-development to stable and **enabled by default** in PR #17153, merged 2026-04-16. It can be
  toggled with `codex --enable image_generation` / `--disable image_generation` or
  `[features] image_generation = true|false` in `$CODEX_HOME/config.toml`.
- Underlying model since 2026-04-21: **gpt-image-2** (replaced gpt-image-1.5; DALL-E 2/3 retired
  from the API 2026-05-12). gpt-image-1 is no longer the default anywhere.
- A bundled system skill **`$imagegen`** (`codex-rs/skills/src/assets/samples/imagegen/SKILL.md`,
  mirrored at `openai/skills/skills/.system/imagegen`) wraps the tool with a workflow. It has two modes:
  1. **Built-in mode (default)** - uses `image_gen`, *no `OPENAI_API_KEY` required*.
  2. **Fallback CLI mode** - `scripts/image_gen.py generate|edit|generate-batch`, calls the
     Images API directly, *requires `OPENAI_API_KEY`* (token billing). Only used on explicit request.
- gpt-image-2 sizes (CLI mode): 1024x1024, 1536x1024, 1024x1536, 2048x2048, 2048x1152, 3840x2160
  (4K beta, >2560x1440 flagged experimental); quality low/medium/high/auto. Transparent background:
  built-in tool supports it; gpt-image-2 via API does not (`background=transparent` unsupported).

### Non-interactive command

```bash
# from the target project directory
codex exec --skip-git-repo-check --sandbox workspace-write -a never \
  -C "$PWD" -o /tmp/last.txt \
  'Use $imagegen to generate a 1024x1024 PNG of <prompt>. Copy the result into ./assets/hero-v1.png and report the final path.'
```

- `codex exec` is the documented headless entry point; `--json` emits JSONL events;
  `-o/--output-last-message` writes the final assistant message to a file; `--full-auto` is
  deprecated in favour of `--sandbox workspace-write`; `--yolo` bypasses sandbox (avoid).
- Windows note (community wrapper `NicholasMTElliott/codex-image-gen`): pipe the prompt via stdin
  rather than argv to avoid `codex.cmd` shell-escaping problems; serialize concurrent runs with a
  lock because shared `$CODEX_HOME` state cross-contaminates sessions.

### Output location control

- **Default is NOT the cwd.** The built-in tool writes to `$CODEX_HOME/generated_images/`
  (`~/.codex/generated_images/ig_*.png`). The skill's own policy is "generate first, then move or
  copy the selected output into the workspace; never leave a project-referenced asset only at the
  default path." So the prompt must instruct the agent to copy into the project, and the sandbox
  must allow writes there (`--sandbox workspace-write` with `-C <project>`).
- Fallback CLI mode: `--out PATH` / `--out-dir DIR`; convention is `output/imagegen/`.
- Open bug #28848 (Codex App 26.611 / CLI 0.140-alpha, June 2026): preview shown but no file saved
  and no path exposed to the agent - a regression. Any adapter must verify the file exists after
  the run rather than trust the assistant's message.

### Auth requirement

- **Works with ChatGPT subscription login** (`codex login`, browser OAuth or `--device-auth`).
  Plans: Plus, Pro, Business, Edu, Enterprise. **Not available on Free.** No API key needed.
- Image turns consume the plan's rolling 5-hour / weekly limits at roughly **3-5x** a text turn;
  Plus is described as tight for ~20-image batches, Pro recommended for heavier use.
- API-key login (`codex login --with-api-key`) also works and bills per image; custom providers
  (`wire_api = "responses"`, Azure, proxies) cannot use the hosted tool (issue #24465).
- **Reliability caveat:** several open issues report the tool simply not being provisioned in a
  session even with ChatGPT login, `image_generation` reported as `stable true`, and the account
  generating images fine on chatgpt.com: #37496 (CLI 0.147.0, Windows 11), #28102 (Plus, Windows,
  Codex App 26.609), #28848 (macOS, no file saved). No maintainer responses recorded at time of check.
  Treat availability as "usually" not "always"; an adapter needs a detection step and a fallback.

### Subscription-only alternatives that bypass the agent loop

- `jdmnk/codex-imagegen-cli` (Python, alpha 0.1.0): reads `~/.codex/auth.json`, refreshes the
  ChatGPT token, POSTs to `https://chatgpt.com/backend-api/codex/responses` and streams the PNG
  from `image_generation_call.result`. `codex-imagegen generate --prompt "..." --out out.png`
  (`--out-dir`, `--output-format png|webp`, `--model`). Deterministic output path, no LLM in the loop,
  but depends on undocumented internals and may break on any Codex update.
- `leeguooooo/chatgpt-imagegen` (zero-dep Python) and `NicholasMTElliott/codex-image-gen`
  (Node; wraps `codex exec --full-auto --cd <tmp>`, strips `OPENAI_API_KEY` from the env to force
  subscription routing, copies result to `--out`) are similar community wrappers.

### Sources

- https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/imagegen/SKILL.md
- https://github.com/openai/skills/blob/main/skills/.system/imagegen/SKILL.md
- https://github.com/openai/codex/pull/17153 (image generation on by default, merged 2026-04-16)
- https://learn.chatgpt.com/docs/developer-commands?surface=cli (codex exec / login flags)
- https://learn.chatgpt.com/docs/config-file/config-advanced (features table)
- https://help.openai.com/en/articles/11381614-codex-cli-and-sign-in-with-chatgpt
- https://github.com/openai/codex/issues/37496 , /issues/28102 , /issues/28848 , /issues/24465 , /issues/21952
- https://codex.danielvaughan.com/2026/04/27/codex-cli-image-generation-gpt-image-2-visual-development-workflows/
- https://github.com/jdmnk/codex-imagegen-cli
- https://github.com/NicholasMTElliott/codex-image-gen
- https://github.com/leeguooooo/chatgpt-imagegen

---

## 2. Google Gemini CLI (`gemini`)

**Capability: PARTIAL - via extension only, and only with a paid Gemini API key. NO on a Google
account / Google AI Pro subscription.**

### Mechanism

- Gemini CLI has **no built-in image generation tool**. Built-in tools (docs/tools/) are:
  file-system, shell, web-fetch, web-search, memory, todos, planning, ask-user, activate-skill,
  mcp-server, mcp-resources, internal-docs, tracker.
- The official extension **`gemini-cli-extensions/nanobanana`** adds an MCP server with slash
  commands `/generate`, `/edit`, `/restore`, `/icon`, `/pattern`, `/story`, `/diagram`, `/nanobanana`.
  Install: `gemini extensions install https://github.com/gemini-cli-extensions/nanobanana`.
  Models: `gemini-3.1-flash-image-preview` (default, "Nano Banana 2"), `gemini-3-pro-image-preview`,
  `gemini-2.5-flash-image` (select via `NANOBANANA_MODEL`). Max 8 variations per command. Node 20+.
- Any other MCP server that calls the Gemini API image models (e.g. `Aeven-AI/mcp-nanobanana`,
  `gemini-imagen` CLI) can be wired in via `settings.json` `mcpServers`; same auth constraints apply.
- Imagen 3 series is being deprecated mid-2026; not a viable target.

### Non-interactive command

```bash
NANOBANANA_API_KEY=... gemini -p '/generate "a flat vector hero illustration" --style minimal' \
  --approval-mode yolo --output-format json
```

Headless mode is triggered by `-p/--prompt` or a non-TTY. Extension MCP tools load in headless
mode like any other MCP server (approval must be auto: `--approval-mode yolo` or per-tool allow).

### Output location control

- The extension writes to **`./nanobanana-output/`** relative to the cwd, created on first use;
  filenames are derived from the prompt (`sunset_over_mountains.png`) with a numeric suffix on
  collision. PNG by default. No documented flag to pick an arbitrary output path; an adapter should
  glob the directory before/after and move the new file.

### Auth requirement

- The nanobanana extension **requires `NANOBANANA_API_KEY`** (a Google AI Studio key). It does not
  ride on the CLI's own OAuth session.
- **Image models have no free tier**: Gemini API pricing lists gemini-2.5-flash-image at $0.039/image,
  gemini-3.1-flash-image at $0.067 per 1K image ($0.045 0.5K, $0.101 2K, $0.151 4K), gemini-3-pro-image
  at $0.134 per 1K/2K, $0.24 per 4K, each marked "Free tier: not available". So a billing-enabled
  Google Cloud project / AI Studio paid key is mandatory.
- **"Login with Google" is dead for consumers.** Google's deprecation notice states that on
  **2026-06-18** Gemini Code Assist stopped serving Gemini CLI requests for "Gemini Code Assist for
  individuals, Google AI Pro, and Google AI Ultra" tiers; only Standard/Enterprise Code Assist
  licences keep OAuth login. Consumers are pointed to the closed-source **Antigravity CLI** (no
  feature parity at launch). Open issue #28229 (P1, 2026-07-01) confirms the error
  "This client is no longer supported for Gemini Code Assist for individuals". A Google account or
  Google AI Pro subscription therefore does not give Gemini CLI image generation at all.

### Sources

- https://github.com/gemini-cli-extensions/nanobanana
- https://github.com/google-gemini/gemini-cli/tree/main/docs/tools (built-in tool list)
- https://geminicli.com/docs/cli/headless/
- https://geminicli.com/docs/get-started/authentication/
- https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals
- https://github.com/google-gemini/gemini-cli/issues/28229
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/image-generation
- https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-image

---

## 3. GitHub Copilot CLI (`copilot`) - brief

**Capability: NO natively; PARTIAL via third-party MCP servers with separate auth.**

- Copilot CLI has no image generation tool. It supports MCP servers (`copilot mcp add NAME -- CMD`,
  `~/.copilot/mcp-config.json`, repo-level `.mcp.json`/`.github/mcp.json`) and a prompt mode
  `copilot -p "..."`; project MCP servers load in prompt mode only for trusted dirs
  (`GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP=true` to force).
- Community `artlovan/copilot_image_gen_mcp` connects to the *Microsoft 365 Copilot* image backend
  (DALL-E) over undocumented WebSocket APIs, authenticating with a Microsoft 365 account via a
  Playwright-driven Edge/Chrome login and ~90-day cached refresh tokens. Requires an M365 Copilot
  licence with image generation enabled - the GitHub Copilot subscription itself does not cover it.
  Output: `~/.copilot-images/<session>/NNN.png`, not the cwd. Explicitly "not affiliated with or
  supported by Microsoft"; may break without notice.
- Any OpenAI-Images or Gemini MCP server also works here, but again on a pay-per-use API key.

Sources: https://github.com/github/copilot-cli ,
https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers ,
https://github.com/artlovan/copilot_image_gen_mcp ,
https://www.wireflow.ai/blog/github-copilot-image-generation

---

## Summary matrix

| CLI | Raster gen | Mechanism | Subscription login OK? | Output dir default | Headless |
|---|---|---|---|---|---|
| Codex 0.153 | Yes | built-in `image_gen` (gpt-image-2) via `$imagegen` skill | **Yes** - ChatGPT Plus/Pro/Business/Edu/Ent (not Free); 3-5x quota cost | `~/.codex/generated_images/`; agent must copy into cwd | `codex exec --sandbox workspace-write -a never -C . -o file` |
| Gemini 0.58 | Partial | `nanobanana` extension (MCP) or any Gemini-API MCP | **No** - needs paid AI Studio API key; consumer OAuth ended 2026-06-18 | `./nanobanana-output/<slug>.png` | `gemini -p ... --approval-mode yolo` |
| Copilot CLI | No / partial | third-party MCP (M365 Copilot or API-key backends) | No (GitHub Copilot sub does not include it) | `~/.copilot-images/` | `copilot -p ...` |

---

## Recommendation for council `assets` role

Only **Codex** satisfies "subscription login, no API key, raster output" today, and even it is
best-effort. A raster-image adapter for the `assets` role should:

1. **Provider order:** Codex (ChatGPT login) first; Gemini `nanobanana` second only when
   `NANOBANANA_API_KEY`/`GEMINI_API_KEY` is set (opt-in paid path); otherwise return a structured
   "no raster provider available" so the council can fall back to SVG/CSS-authored assets.
2. **Preflight for Codex:** `codex login status` (or presence of `~/.codex/auth.json`), check
   `[features] image_generation` not disabled, and record `codex --version`. Do not rely on the
   `image_gen` tool being provisioned - issues #37496/#28102 show it can be silently absent on
   Windows. Probe once per session with a tiny prompt and cache the result.
3. **Invocation:** run `codex exec` from a per-job temp workspace (`-C <tmp>`), `--sandbox
   workspace-write -a never --skip-git-repo-check -o <tmp>/last.md`, prompt piped on stdin
   (Windows `codex.cmd` quoting), prompt text instructing: use `$imagegen` built-in mode, target
   size/format, and *copy the result to `<tmp>/out/<name>.png` and print the absolute path*.
   Strip `OPENAI_API_KEY` from the child env to guarantee subscription routing (and avoid the
   skill's paid fallback firing silently). Serialize runs with a lock file.
4. **Post-run verification (mandatory):** ignore the assistant's claim; glob `<tmp>/out/*.png` and
   as a secondary source diff `~/.codex/generated_images/` before/after (newest `ig_*.png`). Validate
   PNG magic bytes and dimensions (Pillow or `file`). Only then move into the project cwd with the
   council's deterministic filename. Fail closed if nothing landed (bug #28848 pattern).
5. **Cost/limits handling:** treat every image as 3-5 text turns of ChatGPT quota; expose a
   per-run image budget (e.g. max 4) and surface 401/429 (session expired / rolling cap) as
   retryable-later, not as hard failures. Warn that Plus users will hit the 5-hour cap fast.
6. **Gemini path (optional, paid):** `gemini -p '/generate "..."' --approval-mode yolo` with
   `NANOBANANA_API_KEY`; collect new files from `./nanobanana-output/` and move. Document clearly
   that a Google account or AI Pro subscription does *not* work (OAuth ended 2026-06-18) and that
   every image costs ~$0.04-0.15.
7. **Do not build on undocumented endpoints** (`chatgpt.com/backend-api/codex/responses` wrappers,
   M365 Copilot WebSocket) in the plugin itself; at most mention them as user-installed optional
   providers behind an explicit flag, because they break on vendor updates and may violate ToS.
8. **Capabilities to advertise:** PNG (default), WebP (Codex), transparent PNG (Codex built-in
   only), sizes up to 2048x2048 reliably (Codex) / 4K preview (both, experimental). JPG must be a
   local post-conversion step - neither tool emits JPEG natively by default.
