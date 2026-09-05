# Research: Obsidian + Claudian as a "mastermind" vault for `council`

Date checked: 2026-09-05. Web research only (GitHub, community.obsidian.md, obsidian.md/help, forum, source files of the
plugin at `main`); nothing was installed or run. Items marked **(unverified)** rest on one secondary source or were
inferred from code without being executed. Local check: `%APPDATA%\obsidian\obsidian.json` on this machine was read
once (read-only) to confirm the structure in §5.

## 0. Sources

| Source | URL |
|---|---|
| Claudian repo (official, MIT) | https://github.com/YishenTu/claudian |
| Claudian site / docs (only `/docs/collab-mode/` published at check time) | https://claudian.md/ , https://claudian.md/docs/collab-mode/ |
| Community plugin page | https://community.obsidian.md/plugins/realclaudian |
| `manifest.json` (v2.2.5) | https://raw.githubusercontent.com/YishenTu/claudian/main/manifest.json |
| `package.json` (deps) | https://raw.githubusercontent.com/YishenTu/claudian/main/package.json |
| Releases | https://github.com/YishenTu/claudian/releases |
| Source files read for paths | `src/core/bootstrap/storagePaths.ts`, `src/providers/claude/storage/{StorageService,CCSettingsStorage,SlashCommandStorage,SkillStorage,AgentVaultStorage,LegacyMcpConfigCleanup}.ts`, `src/providers/claude/config/ClaudeConfigDir.ts`, `src/providers/claude/plugins/PluginManager.ts`, `src/providers/claude/execution/ClaudeExecutionRequestEncoder.ts`, `src/core/prompt/mainAgent.ts`, `src/core/types/settings.ts` |
| Fork: Oh My Claudian (`oh-my-claudian`) | https://github.com/lee259/oh-my-claudian , https://community.obsidian.md/plugins/oh-my-claudian |
| Third-party write-ups | https://www.dsebastien.net/claudian-plugin-for-obsidian/ (2026-05-26, upd. 06-02), https://parazettel.com/articles/tldr-claude-code-in-obsidian/ (2026-03-30) |
| Obsidian: how data is stored | https://obsidian.md/help/Files+and+folders/How+Obsidian+stores+data |
| Forum: `obsidian.json` structure | https://forum.obsidian.md/t/obsdian-json-automatic-vault-configuration/32700 , https://forum.obsidian.md/t/using-the-obsidian-appdata-folder-for-unit-testing/54241 |
| Forum: Snap/Flatpak paths | https://forum.obsidian.md/t/obsidian-linux-snap-issue-and-flatpak-info/94705 |
| Community plugin registry (7 287 entries) | https://raw.githubusercontent.com/obsidianmd/obsidian-releases/master/community-plugins.json |
| Local REST API with MCP (v5.1.0) | https://github.com/coddingtonbear/obsidian-local-rest-api |
| Advanced URI (v2.0.0) | https://github.com/Vinzent03/obsidian-advanced-uri , https://publish.obsidian.md/advanced-uri-doc |
| REST and MCP server (dsebastien) | https://community.obsidian.md/plugins/cli-rest-mcp |
| Dataview | registry id `dataview`, repo `blacksmithgu/obsidian-dataview` |

## 1. What Claudian is

- Obsidian community plugin by Yishen Tu. Registry entry: `id: realclaudian`, name "Claudian", repo `yishentu/claudian`,
  flagged "not manually reviewed by Obsidian staff". v2.2.5 released 2026-08-30; ~2M downloads; 15.2k stars.
  Desktop only, `minAppVersion 1.13.0`. Releases roughly weekly (2.2.1-2.2.5 between 2026-08-20 and 08-30).
- **It embeds the Claude Agent SDK, not a chat API.** `package.json` depends on `@anthropic-ai/claude-agent-sdk 0.3.226`
  and `@modelcontextprotocol/sdk ~1.30`. The Claude provider spawns the locally installed **Claude Code CLI** (auto-detected,
  or Settings → Advanced → "Claude CLI path"; `findClaudeCLIPath.ts`, `customSpawn.ts`). Requires an existing Claude
  subscription / API key (or OpenRouter, Kimi, GLM, DeepSeek). Other "harnesses" are pluggable: Codex CLI (app-server
  JSON-RPC), Grok Build (ACP), OpenCode, Pi.
- **The vault root is `cwd`.** The SDK query is built with `cwd: vaultWorkingDirectory`, a Claudian system prompt
  ("You are Claudian, operating inside <user>'s Obsidian Vault… Vault absolute path: …"), `permissionMode`
  (Claudian `yolo` → SDK `bypassPermissions`; `plan` → `plan`; default asks), `disallowedTools`, `settingSources` and
  optional `hooks` (a read-only policy is enforced via a `PreToolUse` hook when in restricted mode). So yes: it reads,
  writes, searches vault notes and runs bash, with tool-call outputs shown in a sidebar chat.
- Features (README): sidebar chat with tabs and persistent sessions; inline edit with word-level diff; slash commands
  (`/`) and skills (`$`) from user and vault scope; `@mention` of files, subagents, external directories; Plan Mode
  (Shift+Tab); `/instruction` mode; MCP servers via the provider's native config; Collab Mode (experimental, LAN + git);
  Mermaid rendering; 10 locales. No telemetry claimed.
- The system prompt instructs the agent to reference vault files as wikilinks (`[[folder/note.md]]`), which is relevant
  when we write notes it will link to.

## 2. Install layout and detection (verified from source unless noted)

| Item | Path (relative to vault root) |
|---|---|
| Plugin folder | `.obsidian/plugins/realclaudian/` (`manifest.json`, `main.js`, `styles.css`, `data.json`). README's dev instruction clones to `.obsidian/plugins/claudian` — the folder name is *not* guaranteed; match on `manifest.json → id == "realclaudian"`. |
| Enabled flag | `.obsidian/community-plugins.json` is a JSON array of enabled plugin ids; contains `"realclaudian"` when enabled. |
| Claudian settings | `.claudian/claudian-settings.json` (`CLAUDIAN_SETTINGS_PATH`). Legacy: `.claude/claudian-settings.json`. `data.json` in the plugin folder holds device/machine state only. |
| Session history | under `.claudian/` (legacy `.claude/sessions`); per-device keys; sidecar suffixes `.inputs.json`, `.deleted.json`, `.assigned.json`. |
| Claude Code project settings | `.claude/settings.json` (`CC_SETTINGS_PATH`, written with `$schema: https://json.schemastore.org/claude-code-settings.json`; Claudian manages `permissions` there). |
| Slash commands | `.claude/commands/*.md` (`COMMANDS_PATH`) — same format as Claude Code project commands. |
| Skills | `.claude/skills/<name>/SKILL.md` (`SKILLS_PATH`). |
| Subagents | `.claude/agents/<name>.md` (`AGENTS_PATH`); frontmatter keys `name, description, tools, disallowedTools, model, skills, permissionMode, hooks`. |
| MCP | `.claude/mcp.json` is **legacy** (`LegacyMcpConfigCleanup.ts`); current versions use the CLI's own MCP config (`~/.claude.json` project entries / `.mcp.json`) — "CLI-managed MCP configuration". |
| Claude Code plugins | read from `{CLAUDE_CONFIG_DIR|~/.claude}/plugins/installed_plugins.json` and `settings.json` (`PluginManager.ts`) — Claudian **surfaces Claude Code plugins' agents** inside Obsidian. |
| `CLAUDE.md` | not written by Claudian itself; because `cwd` is the vault and `settingSources` is passed to the SDK, a vault-root `CLAUDE.md` is loaded as project instructions **(unverified — the `resolveClaudeSettingSources` file was not fetched; third-party guides confirm the behaviour in practice)**. Claudian also keeps `CLAUDE.md`/`AGENTS.md` per source folder in its own repo. |

Key `claudian-settings.json` fields (from `ClaudianSettings` interface): `userName`, `permissionMode`, `model`,
`thinkingBudget`, `effortLevel`, `systemPrompt`, `excludedTags`, `mediaFolder`, `persistentExternalContextPaths`,
`sharedEnvironmentVariables`, `envSnippets`, `providerConfigs`, `settingsProvider`, `collabEnabled`,
`collabProjectsFolder`, `collabGitPath`, `pinnedLinkedContentPaths`, `hiddenProviderCommands`, plus UI flags.

**Detection recipe for a third-party tool** (all read-only, no Obsidian API needed):
1. Find vaults from the global registry (§5). 2. For each vault: Claudian present ⇔ any
`.obsidian/plugins/*/manifest.json` has `id` in `{realclaudian, oh-my-claudian}`; enabled ⇔ that id is in
`.obsidian/community-plugins.json`; configured ⇔ `.claudian/claudian-settings.json` exists. 3. Also useful:
`dataview` and `obsidian-local-rest-api` in the same array.

## 3. How Claudian exposes Claude Code features

- **Custom commands / skills / agents**: plain Claude Code project files in the vault's `.claude/` (table above).
  Anything a plugin or tool drops there appears in Claudian's `/`, `$`, `@` pickers. `persistentExternalContextPaths`
  lets the user pin an external directory (e.g. a code repo) so the agent may read it from inside the vault session.
- **Vault instructions**: vault-root `CLAUDE.md` (community practice: describe vault structure, "sacred" human-only
  folders, where the AI may write). Per-session extra instructions via the `systemPrompt` setting and `/instruction`.
- **Hooks**: Claudian passes `hooks` to the SDK for its own read-only guard and accepts `hooks` in agent frontmatter;
  user hooks in `.claude/settings.json` are honoured by the SDK when `settingSources` includes `project` **(unverified)**.
- **MCP**: whatever the Claude CLI has configured for the vault project (`claude mcp add` in the vault dir).

## 4. Fork to watch

`oh-my-claudian` (id and folder `oh-my-claudian`, author "Lee", repo `lee259/oh-my-claudian`) — a maintained fork adding
Cursor Agent and Oh My Pi providers. Same vault contract as far as visible; treat as equivalent for detection.

## 5. How Obsidian records vaults

Global config directory (obsidian.md/help + forum):

| OS | Path |
|---|---|
| Windows | `%APPDATA%\obsidian\` (help page spells it `Obsidian`; NTFS is case-insensitive — on this machine the folder is `C:\Users\<u>\AppData\Roaming\obsidian`) |
| macOS | `~/Library/Application Support/obsidian/` |
| Linux (deb/AppImage) | `$XDG_CONFIG_HOME/obsidian/` or `~/.config/obsidian/` |
| Linux Flatpak | `~/.var/app/md.obsidian.Obsidian/config/obsidian/` |
| Linux Snap | `~/snap/obsidian/current/.config/obsidian/` |

`obsidian.json` (verified locally, paths redacted):

```json
{ "vaults": {
    "df74a5a9156e4c49": { "path": "C:\\...\\VaultA", "ts": 1786434604574 },
    "d21e27b5fa95883f": { "path": "C:\\...\\VaultB", "ts": 1786781742903, "open": true } } }
```

- Key = 16-hex random vault id (also the name of `<id>.json` sidecars holding per-vault window state); `path` absolute;
  `ts` = last-opened epoch ms; `open` present only for currently open vaults. Other keys like `insider`/`updateDisabled`
  may appear at top level **(unverified)**. Edit only when Obsidian is closed; prefer read-only use.
- Per vault: `.obsidian/` holds `app.json`, `community-plugins.json`, `core-plugins.json`, `plugins/<id>/`,
  `workspace.json`. The vault *name* is the folder's basename (used by `obsidian://` URIs).

## 6. External write paths into a vault

Three standard options, in order of preference for an automated tool:

1. **Direct file write.** A vault is a folder of Markdown; Obsidian watches the filesystem and picks up changes live.
   Zero dependencies, works when Obsidian is closed. Only caveat: write atomically (temp + rename) and never touch
   `.obsidian/`. This is what Claudian itself does (via the SDK's Write tool).
2. **Local REST API with MCP** (`obsidian-local-rest-api`, v5.1.0, Adam Coddington). HTTPS `127.0.0.1:27124`
   (optional HTTP 27123), `Authorization: Bearer <api-key>`; `GET /` unauthenticated returns status (detection);
   `PUT/PATCH/GET/DELETE /vault/{path}`, PATCH targets heading/block/frontmatter key; `POST /search/`, `/commands/{id}/`,
   `/open/{path}`; built-in MCP server at `/mcp/` (Streamable HTTP). Needed only when you want Obsidian-side effects
   (run a command, open a note, search index) rather than plain writes. Requires Obsidian running.
3. **Advanced URI** (`obsidian-advanced-uri`, v2.0.0): `obsidian://adv-uri?vault=<name>&filepath=<f>&data=<txt>&mode=append|prepend|overwrite`,
   `&heading=`, `&commandid=`. Good for "open this note" from a CLI; poor for bulk writes (URL length, needs the app
   running, fire-and-forget). `cli-rest-mcp` (dsebastien) is a newer alternative to (2).

Verdict: use (1) for mirroring, optionally (3) to open a note, (2) only if the user already has it (never require it).

## 7. Proposal: an Obsidian vault as the `council` mastermind

**Goal.** The repo stays the source of truth for execution (`.council/`, `MEMORY.md`, `LESSONS.md`, `reports/`).
The vault is the cross-project *thinking* layer: where Pawel plans, reviews decisions, and where Claudian (or plain
Claude Code opened in the vault) can query everything with Dataview. Mirror is one-way repo → vault for machine-generated
notes, one-way vault → repo for human planning notes; never two-way sync of the same file.

**Configuration (`.council/council.json`).**
`obsidian: { vault: "<abs path or null=auto>", project_folder: "Projects/<repo-name>", mirror: ["tasks","reports","decisions","handoffs","lessons"], read_context: true }`.
Auto-detect: parse `obsidian.json` (§5), prefer the `open: true` vault, else newest `ts`; ask before first write.
`council doctor` prints: vault found / Claudian installed+enabled / Dataview / Local REST API.

**Notes written to the vault (all with YAML frontmatter for Dataview; `type` + `project` on every note).**

| Repo artefact | Vault note | Frontmatter |
|---|---|---|
| `.council/tasks/<id>.json` | `Projects/<repo>/Tasks/<id>.md` (one card per task, rewritten on every state change) | `type: council-task, project, id, title, status, model, role, attempt, privacy, scope, branch, created, updated, depends_on, epic` |
| `reports/<id>/REPORT.md` + `gates.json` | appended to the task card under `## Reports` (latest first) or `Tasks/<id>/report-<attempt>.md` if large | `type: council-report, id, attempt, status, gates_ok, duration_min, tokens` |
| `MEMORY.md` decision entries | `Projects/<repo>/Decisions/YYYY-MM-DD-<slug>.md`, one per decision | `type: decision, project, date, status: accepted/superseded, supersedes, tags` |
| handoff notes (`council_handoff`) | `Projects/<repo>/Handoffs/YYYY-MM-DD-HHMM.md` | `type: handoff, project, from_model, to_model, task_ids, open_questions` |
| `LESSONS.md`, `.council/stats.json` | `Projects/<repo>/Lessons.md` (regenerated), `Council/Models/<model>.md` (trust per model across projects) | `type: lesson / model-profile, model, role, trust, wins, defects` |
| project overview | `Projects/<repo>/<repo>.md` hub note with Dataview blocks: open tasks by status, last 10 decisions, blocked tasks awaiting answer | `type: project, repo_path, base_branch, phase` |

Privacy gate: tasks with `privacy: local-only` are mirrored as stubs (id, status, title) and reports are never copied;
`never_share` content is stripped exactly as for executors. The mirror is a `hooks`-free post-step in `store.py`/`council_merge`
(one `obsidian.py` module, atomic writes, vault path from config), plus a `council obsidian sync` CLI for a full rebuild.

**Vault notes read as planning context.** `council_plan` (and `/council:plan`) pull, when present:
`Projects/<repo>/Plan.md` (human roadmap, Now/Next/Later), `Projects/<repo>/Decisions/*` with `status: accepted`
(constraints), `Projects/<repo>/Questions.md` (open questions the planner must answer or turn into `blocked` tasks),
`Council/Playbooks/*.md` (user playbooks authored in the vault, exported to `.council/playbooks/`), and `Council/Charter.md`
(global rules → merged into TASK.md after `CHARTER.md`). Size-cap the injected text (e.g. 8 kB) and cite note paths in
the resulting task cards (`context: [[Projects/repo/Decisions/...]]`).

**How Claudian users interact.** Because Claudian runs Claude Code in the vault, the plugin ships a small vault-side kit,
installed by `council init --obsidian`: `.claude/commands/council-status.md` (summarise open task cards via Dataview
frontmatter), `council-decide.md` (write a Decision note in the right format), `council-ask.md` (append to Questions.md),
and a vault `CLAUDE.md` section describing the `Projects/<repo>/` layout and the rule "machine notes under Tasks/ and
Handoffs/ are read-only mirrors; edit Plan.md, Decisions/, Questions.md". Optionally register `council-mcp` in the vault
project via `claude mcp add`, so from Claudian the user can call `council_status`/`council_answer` directly (the MCP
server must then accept an explicit `repo` argument or read it from the hub note's `repo_path`). Answering a `blocked`
task from Obsidian = editing the task card's `## Answer` section; the repo-side watcher picks it up on next `council_answer`
(or the user runs `/council:answer` in the repo). Keep it explicit rather than a filesystem watcher on the vault.

**When Claudian is absent.** Detection per §2. If no vault: do nothing, mention `council init --obsidian` once in
`doctor`. If a vault exists but Claudian is missing: still mirror (plain Markdown is useful with Dataview alone) and
suggest "Install *Claudian* (id `realclaudian`) or *Oh My Claudian* to run Claude Code inside the vault; then
`council init --obsidian` installs the vault commands". If Dataview is missing, also generate a static
`Projects/<repo>/Dashboard.md` table so the hub note is readable without it. Never require Local REST API; if it is
detected and running (`GET https://127.0.0.1:27124/`), offer `council open <id>` to jump to the task card via
`obsidian://open?vault=<name>&file=<path>` (core URI, no plugin needed) — Advanced URI only if the user has it.

**Open decisions for DESIGN.md.** (a) Is the vault per user (global `Council/` folder) or per repo? Proposal: both,
`Council/` for cross-project model trust and playbooks, `Projects/<repo>/` per repo. (b) Should Decisions be
authored in the vault and mirrored into `MEMORY.md`, or the reverse? Proposal: authored wherever, but `MEMORY.md`
remains canonical and the vault note carries `source: memory|vault` to avoid loops. (c) Phase: after v1.0; smallest
useful slice = hub note + task cards + decisions mirror + `doctor` detection.
