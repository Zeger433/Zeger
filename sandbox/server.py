"""Runs inside the sandbox container: a shell and a browser behind a tiny HTTP API.
The port is only reachable from the backend container."""
import asyncio, base64, contextlib, os, signal, tempfile
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
WORKSPACE = os.environ.get("WORKSPACE_DIR", "/workspace")
lock = asyncio.Lock()
page = None  # shortcut: one shared browser page, started on first use


def clip(s, n=20000):
    return s if len(s) <= n else s[: n // 2] + f"\n...[{len(s) - n} chars cut]...\n" + s[-n // 2 :]


@app.get("/health")
def health():
    return {"ok": True}


class Exec(BaseModel):
    command: str
    timeout: int = 120


@app.post("/exec")
async def run(r: Exec):
    timeout = min(max(r.timeout, 1), 900)
    with tempfile.TemporaryFile() as out:  # a file, not a pipe, so `cmd &` can't keep us waiting
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", r.command, cwd=WORKSPACE, stdin=asyncio.subprocess.DEVNULL,
            stdout=out, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
        note = ""
        try:
            await asyncio.wait_for(proc.wait(), timeout)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
            note = f"\n[killed after {timeout}s]"
        out.seek(0)
        return {"output": clip(out.read().decode(errors="replace")) + note, "exit_code": proc.returncode}


class Browse(BaseModel):
    action: str
    url: Optional[str] = None
    index: Optional[int] = None
    text: Optional[str] = None
    key: Optional[str] = None
    direction: Optional[str] = None


def target(r):
    return f'[data-aid="{r.index}"]'


ACTIONS = {
    "goto": lambda r: page.goto(r.url, wait_until="domcontentloaded", timeout=30000),
    "click": lambda r: page.click(target(r), timeout=5000),
    "type": lambda r: page.fill(target(r), r.text or "", timeout=5000),
    "press": lambda r: page.keyboard.press(r.key or "Enter"),
    "scroll": lambda r: page.mouse.wheel(0, -600 if r.direction == "up" else 600),
    "back": lambda r: page.go_back(),
    "read": lambda r: asyncio.sleep(0),
}

# Numbers the visible interactive elements so the model can say "click 3".
LIST_JS = """() => {
  document.querySelectorAll('[data-aid]').forEach(e => e.removeAttribute('data-aid'));
  const found = [];
  for (const e of document.querySelectorAll('a[href],button,input,textarea,select,[role=button],[onclick]')) {
    const box = e.getBoundingClientRect();
    if (box.width < 2 || box.height < 2 || getComputedStyle(e).visibility === 'hidden') continue;
    e.setAttribute('data-aid', found.length);
    found.push({i: found.length, tag: e.tagName.toLowerCase(), href: e.getAttribute('href') || '',
      text: (e.innerText || e.value || e.placeholder || e.getAttribute('aria-label') || '').trim().slice(0, 60)});
    if (found.length >= 60) break;
  }
  return found;
}"""


@app.post("/browser")
async def browse(r: Browse):
    global page
    async with lock:
        if page is None:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = await browser.new_page(viewport={"width": 1100, "height": 700})
        error = None
        try:
            await ACTIONS[r.action](r)
            await page.wait_for_timeout(600)
        except Exception as e:  # bad selector, failed navigation: tell the model, don't crash
            error = str(e).splitlines()[0][:300]
        shot = base64.b64encode(await page.screenshot(type="jpeg", quality=60)).decode()
        return {"url": page.url, "title": await page.title(), "error": error, "screenshot": shot,
                "text": clip(await page.inner_text("body"), 4000), "elements": await page.evaluate(LIST_JS)}
