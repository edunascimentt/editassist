# AGENTS.md (Codex and other agents)

Same instructions as Claude Code: read and follow `CLAUDE.md` in this folder. Skills live in
`.claude/skills/<name>/SKILL.md`; when a task matches a skill's description, open that file and
follow it.

Live DaVinci Resolve control (resolve-live skill): Claude Code reads `.mcp.json`. For Codex, add to
`~/.codex/config.toml`, with the absolute path of this folder:

```toml
[mcp_servers.davinci-resolve]
command = "uv"
args = ["run", "--quiet", "--directory", "/path/to/editassist", "ea", "resolve-mcp"]
```
