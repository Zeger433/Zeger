import asyncio, contextlib
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from agent import Agent

app = FastAPI()


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()

    async def emit(event):
        with contextlib.suppress(Exception):  # the tab may have closed mid-run
            await sock.send_json(event)

    agent, task = Agent(emit), None  # shortcut: one conversation per open tab, lost on reload
    try:
        while True:
            msg = await sock.receive_json()
            running = task and not task.done()
            if msg["type"] == "user" and not running:
                task = asyncio.create_task(agent.run(msg["text"]))
            elif msg["type"] == "stop" and running:
                task.cancel()
    except WebSocketDisconnect:
        if task:
            task.cancel()


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))  # keep last
