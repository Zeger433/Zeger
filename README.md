# Zeger

A small, open-source AI software engineer you run locally. Give it a task in chat; it works on a folder you choose, inside Docker: it reads and edits files, runs commands and tests, and drives a headless browser while you watch.

## Run it

```bash
cp .env.example .env     # set WORKSPACE (an existing folder), your API key, and on Linux HOST_UID/HOST_GID
docker compose up --build
```

Open http://localhost:8000.

## How it works

- **backend** serves the UI and runs the loop: send the history and tools to the LLM, run the tool calls, stream each step to the page, repeat until the model calls `finish` (`done` or `needs_help`) or hits `MAX_STEPS` (40).
- **sandbox** runs every shell command and the browser. It has no API keys, its port isn't published, and it has memory and process limits.
- Both containers mount only your workspace folder. File tools live in the backend and refuse paths outside it.
- Models go through [litellm](https://docs.litellm.ai), so set `LLM_MODEL` and the matching key in `.env` (needs tool calling).

## Things to know

- The agent can change or delete anything in the workspace folder. Commit first.
- The sandbox has internet access (installs, browsing). Keep secrets out of the workspace.
- Create the workspace folder before starting; Docker would otherwise create it owned by root.
- Tests: `cd backend && pip install -r requirements.txt pytest && pytest`

## Left out on purpose

Live command streaming, a file tree and diff view, saved sessions, context trimming for very long runs, per-task git branches. Places where a shortcut was taken are marked `shortcut:` in the code.

Trimmed following the [Ponytail](https://github.com/DietrichGebert/ponytail) rules (MIT): write what the task needs, reuse what exists, keep validation and security.

