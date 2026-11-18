"""What the agent can do. Files are handled here (the backend mounts the same workspace);
commands and the browser go to the sandbox container."""
import os
from pathlib import Path
import httpx

WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "/workspace")).resolve()
http = httpx.AsyncClient(base_url=os.environ.get("SANDBOX_URL", "http://sandbox:8001"), timeout=960)

text = {"type": "string"}


def tool(name, description, required=(), **props):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": props, "required": list(required)}}}


TOOLS = [
    tool("run_command", "Run a bash command in /workspace; returns output and exit code.", ["command"],
         command=text, timeout={"type": "integer", "description": "seconds, default 120"}),
    tool("read_file", "Read a text file.", ["path"], path=text),
    tool("write_file", "Create or overwrite a file.", ["path", "content"], path=text, content=text),
    tool("edit_file", "Replace the one exact occurrence of old_str with new_str.", ["path", "old_str", "new_str"],
         path=text, old_str=text, new_str=text),
    tool("list_files", "List a directory (default '.').", path=text),
    tool("browser", "Control a headless browser. Returns the page text and numbered interactive elements.", ["action"],
         action={"type": "string", "enum": ["goto", "click", "type", "press", "scroll", "back", "read"]},
         url=text, index={"type": "integer"}, text=text, key=text, direction={"type": "string", "enum": ["up", "down"]}),
    tool("finish", "End your turn: 'done' when complete, 'needs_help' if blocked.", ["status", "summary"],
         status={"type": "string", "enum": ["done", "needs_help"]}, summary=text),
]


def inside(path):
    """Resolve a path and refuse anything outside the workspace."""
    p = (WORKSPACE / path).resolve()
    if WORKSPACE not in (p, *p.parents):
        raise ValueError(f"path is outside the workspace: {path}")
    return p


async def post(path, body):
    r = await http.post(path, json=body)
    r.raise_for_status()
    return r.json()


async def run_tool(name, a):
    """Returns (text for the model, extra fields for the UI). Raises on failure."""
    if name == "run_command":
        r = await post("/exec", {"command": a["command"], "timeout": a.get("timeout", 120)})
        return f"{r['output']}\n[exit code {r['exit_code']}]", {"exit_code": r["exit_code"]}
    if name == "read_file":
        return inside(a["path"]).read_text(errors="replace")[:30000], {}
    if name == "write_file":
        p = inside(a["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["content"])
        return f"Wrote {a['path']}", {}
    if name == "edit_file":
        p = inside(a["path"])
        old = p.read_text()
        n = old.count(a["old_str"])
        if n != 1:
            raise ValueError(f"old_str matches {n} places, it must match exactly one")
        p.write_text(old.replace(a["old_str"], a["new_str"]))
        return f"Edited {a['path']}", {}
    if name == "list_files":
        return "\n".join(sorted(c.name + "/" * c.is_dir() for c in inside(a.get("path", ".")).iterdir())) or "(empty)", {}
    if name == "browser":
        r = await post("/browser", a)
        elements = "\n".join(f"[{e['i']}] <{e['tag']}> {e['text']!r} {e['href']}" for e in r["elements"])
        page = f"URL: {r['url']}\nTitle: {r['title']}\n{r['error'] or ''}\n\n{r['text']}\n\nInteractive elements:\n{elements}"
        return page, {"screenshot": r["screenshot"], "url": r["url"]}
    raise ValueError(f"unknown tool: {name}")
