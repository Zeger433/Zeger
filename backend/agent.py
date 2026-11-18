import asyncio, json, os
import litellm
from tools import TOOLS, run_tool

MODEL = os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-5-5")  # API keys come from the environment
MAX_STEPS = int(os.environ.get("MAX_STEPS", "40"))

SYSTEM = """You are an autonomous software engineer in a sandboxed Linux container. \
The user's project is mounted at /workspace, your working directory.

Explore the code first, make focused changes, then run the tests or the program to check your work. \
Keep going until the task is done and verified.
- edit_file for small changes, write_file for new files.
- run_command is non-interactive bash. Never run anything that waits for input. \
Start servers in the background (`nohup CMD > /tmp/server.log 2>&1 &`) and read the log.
- The browser can open servers you start (http://localhost:PORT). Click and type by element number.
- Blocked, or need a decision? Call finish with status "needs_help" and say what you need.
- Finished? Call finish with status "done" and a short summary.
Keep text between tool calls brief."""


class Agent:
    def __init__(self, emit):
        self.emit = emit
        self.messages = [{"role": "system", "content": SYSTEM}]
        self.done = False

    async def step(self, call):
        """Run one tool call, tell the UI, return the text the model sees."""
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            return "Error: arguments were not valid JSON"
        if name == "finish":
            self.done = True
            await self.emit({**args, "type": "finish"})
            return "ok"
        await self.emit({"type": "action", "id": call.id, "tool": name, "args": args})
        try:
            out, extra = await run_tool(name, args)
        except Exception as e:  # the model gets to see the failure and try something else
            out, extra = f"Error: {e}", {}
        await self.emit({"type": "observation", "id": call.id, "tool": name, "output": out, **extra})
        return out

    async def run(self, text):
        self.messages.append({"role": "user", "content": text})
        self.done = False
        await self.emit({"type": "status", "state": "running"})
        try:
            for _ in range(MAX_STEPS):
                reply = await litellm.acompletion(model=MODEL, messages=self.messages, tools=TOOLS, max_tokens=4096)
                msg = reply.choices[0].message
                if msg.content:
                    await self.emit({"type": "message", "role": "assistant", "text": msg.content})
                if not msg.tool_calls:
                    self.messages.append(msg)
                    break
                results = [{"role": "tool", "tool_call_id": c.id, "content": await self.step(c)} for c in msg.tool_calls]
                # History only grows once every tool in a step has run, so Stop can't leave a dangling tool call.
                # shortcut: a stopped step is forgotten by the model; no context trimming for very long sessions.
                self.messages += [msg, *results]
                if self.done:
                    break
            else:
                await self.emit({"type": "message", "role": "system", "text": f"Paused after {MAX_STEPS} steps. Send a message to continue."})
        except asyncio.CancelledError:
            await self.emit({"type": "message", "role": "system", "text": "Stopped."})
        except Exception as e:
            await self.emit({"type": "message", "role": "error", "text": f"{type(e).__name__}: {str(e)[:600]}"})
        finally:
            await self.emit({"type": "status", "state": "idle"})
