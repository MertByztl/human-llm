# Contributing to human-llm 🧠

Thanks for wanting to help — this is a small, fun project and contributions of
all sizes are welcome. You can be the model *and* the maintainer.

## Ground rules

- **Never commit a `sessions/` file.** Those are real conversations and may hold
  personal data. They're already in `.gitignore` — keep it that way.
- Keep it dependency-light. The server is just FastAPI + uvicorn, and the example
  agent uses only the Python standard library. Please don't add heavy deps
  without a good reason.
- Be kind in issues and PRs. 🙂

## Dev setup

```bash
git clone https://github.com/MertByztl/human-llm.git
cd human-llm
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Open <http://localhost:8000> and you're running. Try it end to end with the demo
agent in another terminal:

```bash
python examples/demo_agent.py
```

### With Docker

```bash
docker build -t human-llm .
docker run -p 8000:8000 -v "$(pwd)/sessions:/app/sessions" human-llm
```

## Making a change

1. Fork the repo and create a branch: `git checkout -b my-change`
2. Make your change. Keep the style consistent with the surrounding code.
3. If it touches the API behaviour, test it against all three dialects
   (OpenAI `/v1/chat/completions`, Anthropic `/v1/messages`, Ollama `/api/chat`).
   A quick `curl` against each is enough.
4. Update the `README.md` if you changed how something works.
5. Open a pull request with a short description of **what** and **why**.

## Ideas / good first issues

- A one-click "copy as curl" button in the UI.
- Multi-request queue handling in the UI (answer several pending calls).
- A proper streaming experience (type-as-you-go instead of one chunk).
- More example clients (LangChain, an Anthropic-SDK example, an Ollama client).
- Light theme toggle.

Have fun — and remember, you are the model. 🧠
