# Examples

Small clients that talk to a running `human-llm` server, so you can watch the
human-in-the-loop flow without wiring up a real agent.

## `demo_agent.py` — STRIX-JR

A tiny Strix-style "autonomous pentest agent" whose brain is you. It sends a few
OpenAI-style requests; you answer each one in the web UI.

```bash
# 1) start the server (from the repo root, in one terminal)
python server.py

# 2) run the demo agent (in another terminal)
python examples/demo_agent.py

# options
python examples/demo_agent.py --steps 5          # more turns
HUMAN_LLM_URL=http://192.168.1.50:8000 python examples/demo_agent.py   # remote box
```

Open <http://localhost:8000> while it runs — each step will pop up there waiting
for your reply. You are the model. 🧠

> Uses only the Python standard library — no extra dependencies.
