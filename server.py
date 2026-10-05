#!/usr/bin/env python3
"""
human-llm - a universal LLM API where the model is YOU.

A tiny human-in-the-loop LLM endpoint that speaks three dialects at once:

  * OpenAI      ->  POST /v1/chat/completions   (and /v1/completions, /v1/models)
  * Anthropic   ->  POST /v1/messages
  * Ollama      ->  POST /api/chat, /api/generate  (and /api/tags, /api/version)

Point ANY of those clients/agents at this server. Every request shows up in a
web UI; you type the answer like a well-meaning carbon-based language model;
the reply is logged to disk and sent back in whatever dialect the caller used.

For testing, learning and fun. You are the model. Be a good one.
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# One JSONL file per server run. Every exchange is appended as it happens, so
# if the human slips up you can hand this file to an AI later and ask
# "why did this go sideways?".
SESSION_FILE = SESSIONS_DIR / f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"

app = FastAPI(title="human-llm", description="You are the model now.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- shared state ----------------------------------------------------------
PENDING: dict[str, dict] = {}            # request_id -> request shown in the UI
WAITERS: dict[str, asyncio.Future] = {}  # request_id -> future with the answer


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def log_exchange(entry: dict) -> None:
    with SESSION_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def flatten(content) -> str:
    """Turn any content shape (str / list of blocks) into display text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    parts.append(block["text"])
                elif "content" in block and isinstance(block["content"], str):
                    parts.append(block["content"])
                else:
                    parts.append(json.dumps(block, ensure_ascii=False))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return json.dumps(content, ensure_ascii=False)


def parse_args(args_str: str):
    try:
        return json.loads(args_str or "{}")
    except Exception:
        return {"_raw": args_str}


async def ask_human(protocol: str, display_messages: list, tools, raw: dict) -> dict:
    """Queue a request for the UI, block until a human answers, log it, return it."""
    req_id = "req-" + uuid.uuid4().hex[:12]
    created = int(time.time())
    PENDING[req_id] = {
        "id": req_id,
        "protocol": protocol,
        "model": raw.get("model", "human-llm"),
        "messages": display_messages,
        "tools": tools,
        "created": created,
        "created_iso": datetime.now(timezone.utc).isoformat(),
    }
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    WAITERS[req_id] = fut
    try:
        answer = await fut
    finally:
        WAITERS.pop(req_id, None)
        PENDING.pop(req_id, None)

    log_exchange(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "request_id": req_id,
            "protocol": protocol,
            "model": raw.get("model", "human-llm"),
            "messages": display_messages,
            "tools": tools,
            "answer": answer,
        }
    )
    answer["_request_id"] = req_id
    return answer


# ===========================================================================
# OpenAI dialect
# ===========================================================================
@app.get("/v1/models")
async def openai_models():
    return {
        "object": "list",
        "data": [
            {"id": "human-llm", "object": "model", "created": int(time.time()), "owned_by": "you"}
        ],
    }


@app.post("/v1/chat/completions")
async def openai_chat(request: Request):
    body = await request.json()
    model = body.get("model", "human-llm")
    messages = [{"role": m.get("role", "user"), "content": flatten(m.get("content"))}
                for m in body.get("messages", [])]
    stream = bool(body.get("stream", False))
    answer = await ask_human("openai", messages, body.get("tools"), body)

    created = int(time.time())
    cmpl_id = "chatcmpl-" + uuid.uuid4().hex[:20]

    if answer.get("type") == "tool":
        tool_call = {
            "id": "call_" + uuid.uuid4().hex[:10],
            "type": "function",
            "function": {"name": answer.get("tool_name") or "unknown",
                         "arguments": answer.get("tool_args") or "{}"},
        }
        message = {"role": "assistant", "content": None, "tool_calls": [tool_call]}
        finish, text = "tool_calls", tool_call["function"]["arguments"]
    else:
        text = answer.get("content", "")
        message = {"role": "assistant", "content": text}
        finish, tool_call = "stop", None

    usage = {"prompt_tokens": approx_tokens(json.dumps(messages, ensure_ascii=False)),
             "completion_tokens": approx_tokens(text)}
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

    if stream:
        async def gen():
            head = {"id": cmpl_id, "object": "chat.completion.chunk", "created": created,
                    "model": model, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
            yield f"data: {json.dumps(head, ensure_ascii=False)}\n\n"
            delta = {"tool_calls": [tool_call]} if tool_call else {"content": text}
            mid = {"id": cmpl_id, "object": "chat.completion.chunk", "created": created,
                   "model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
            yield f"data: {json.dumps(mid, ensure_ascii=False)}\n\n"
            tail = {"id": cmpl_id, "object": "chat.completion.chunk", "created": created,
                    "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}
            yield f"data: {json.dumps(tail, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    return JSONResponse({"id": cmpl_id, "object": "chat.completion", "created": created,
                         "model": model,
                         "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                         "usage": usage})


@app.post("/v1/completions")
async def openai_completions(request: Request):
    body = await request.json()
    model = body.get("model", "human-llm")
    prompt = body.get("prompt", "")
    if isinstance(prompt, list):
        prompt = "\n".join(str(p) for p in prompt)
    answer = await ask_human("openai", [{"role": "user", "content": prompt}], None, body)
    text = answer.get("content", "")
    return JSONResponse({"id": "cmpl-" + uuid.uuid4().hex[:20], "object": "text_completion",
                         "created": int(time.time()), "model": model,
                         "choices": [{"index": 0, "text": text, "finish_reason": "stop"}],
                         "usage": {"prompt_tokens": approx_tokens(prompt),
                                   "completion_tokens": approx_tokens(text),
                                   "total_tokens": approx_tokens(prompt) + approx_tokens(text)}})


# ===========================================================================
# Anthropic dialect
# ===========================================================================
@app.post("/v1/messages")
async def anthropic_messages(request: Request):
    body = await request.json()
    model = body.get("model", "human-llm")
    stream = bool(body.get("stream", False))

    display = []
    system = body.get("system")
    if system:
        display.append({"role": "system", "content": flatten(system)})
    for m in body.get("messages", []):
        display.append({"role": m.get("role", "user"), "content": flatten(m.get("content"))})

    answer = await ask_human("anthropic", display, body.get("tools"), body)

    msg_id = "msg_" + uuid.uuid4().hex[:20]
    in_tok = approx_tokens(json.dumps(display, ensure_ascii=False))

    if answer.get("type") == "tool":
        tool_id = "toolu_" + uuid.uuid4().hex[:16]
        name = answer.get("tool_name") or "unknown"
        args_obj = parse_args(answer.get("tool_args"))
        content = [{"type": "tool_use", "id": tool_id, "name": name, "input": args_obj}]
        stop_reason = "tool_use"
        out_tok = approx_tokens(answer.get("tool_args") or "{}")
    else:
        text = answer.get("content", "")
        content = [{"type": "text", "text": text}]
        stop_reason = "end_turn"
        out_tok = approx_tokens(text)

    if stream:
        async def gen():
            def ev(name, data):
                return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            start_msg = {"type": "message_start",
                         "message": {"id": msg_id, "type": "message", "role": "assistant",
                                     "model": model, "content": [], "stop_reason": None,
                                     "stop_sequence": None,
                                     "usage": {"input_tokens": in_tok, "output_tokens": 0}}}
            yield ev("message_start", start_msg)
            if answer.get("type") == "tool":
                yield ev("content_block_start", {"type": "content_block_start", "index": 0,
                         "content_block": {"type": "tool_use", "id": content[0]["id"],
                                           "name": content[0]["name"], "input": {}}})
                yield ev("content_block_delta", {"type": "content_block_delta", "index": 0,
                         "delta": {"type": "input_json_delta",
                                   "partial_json": json.dumps(content[0]["input"], ensure_ascii=False)}})
            else:
                yield ev("content_block_start", {"type": "content_block_start", "index": 0,
                         "content_block": {"type": "text", "text": ""}})
                yield ev("content_block_delta", {"type": "content_block_delta", "index": 0,
                         "delta": {"type": "text_delta", "text": content[0]["text"]}})
            yield ev("content_block_stop", {"type": "content_block_stop", "index": 0})
            yield ev("message_delta", {"type": "message_delta",
                     "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                     "usage": {"output_tokens": out_tok}})
            yield ev("message_stop", {"type": "message_stop"})
        return StreamingResponse(gen(), media_type="text/event-stream")

    return JSONResponse({"id": msg_id, "type": "message", "role": "assistant", "model": model,
                         "content": content, "stop_reason": stop_reason, "stop_sequence": None,
                         "usage": {"input_tokens": in_tok, "output_tokens": out_tok}})


# ===========================================================================
# Ollama dialect
# ===========================================================================
@app.get("/api/version")
async def ollama_version():
    return {"version": "human-llm-1.0"}


@app.get("/api/tags")
async def ollama_tags():
    return {"models": [{"name": "human-llm:latest", "model": "human-llm:latest",
                        "modified_at": datetime.now(timezone.utc).isoformat(),
                        "size": 0, "details": {"family": "human", "parameter_size": "1 brain"}}]}


@app.post("/api/chat")
async def ollama_chat(request: Request):
    body = await request.json()
    model = body.get("model", "human-llm")
    stream = body.get("stream", True)  # Ollama defaults to streaming
    messages = [{"role": m.get("role", "user"), "content": flatten(m.get("content"))}
                for m in body.get("messages", [])]
    answer = await ask_human("ollama", messages, body.get("tools"), body)
    text = answer.get("content", "") if answer.get("type") != "tool" else (answer.get("tool_args") or "")
    now = datetime.now(timezone.utc).isoformat()

    if stream:
        async def gen():
            chunk = {"model": model, "created_at": now,
                     "message": {"role": "assistant", "content": text}, "done": False}
            yield json.dumps(chunk, ensure_ascii=False) + "\n"
            done = {"model": model, "created_at": now,
                    "message": {"role": "assistant", "content": ""}, "done": True,
                    "done_reason": "stop", "total_duration": 0,
                    "prompt_eval_count": approx_tokens(json.dumps(messages, ensure_ascii=False)),
                    "eval_count": approx_tokens(text)}
            yield json.dumps(done, ensure_ascii=False) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson")

    return JSONResponse({"model": model, "created_at": now,
                         "message": {"role": "assistant", "content": text}, "done": True,
                         "done_reason": "stop",
                         "prompt_eval_count": approx_tokens(json.dumps(messages, ensure_ascii=False)),
                         "eval_count": approx_tokens(text)})


@app.post("/api/generate")
async def ollama_generate(request: Request):
    body = await request.json()
    model = body.get("model", "human-llm")
    stream = body.get("stream", True)
    prompt = body.get("prompt", "")
    answer = await ask_human("ollama", [{"role": "user", "content": prompt}], None, body)
    text = answer.get("content", "")
    now = datetime.now(timezone.utc).isoformat()

    if stream:
        async def gen():
            yield json.dumps({"model": model, "created_at": now, "response": text, "done": False},
                             ensure_ascii=False) + "\n"
            yield json.dumps({"model": model, "created_at": now, "response": "", "done": True,
                              "done_reason": "stop"}, ensure_ascii=False) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson")

    return JSONResponse({"model": model, "created_at": now, "response": text, "done": True,
                         "done_reason": "stop"})


# ===========================================================================
# UI-facing endpoints
# ===========================================================================
@app.get("/api/pending")
async def get_pending():
    items = sorted(PENDING.values(), key=lambda x: x["created"])
    return {"pending": items, "session_file": SESSION_FILE.name}


@app.post("/api/respond")
async def respond(request: Request):
    data = await request.json()
    fut = WAITERS.get(data.get("id"))
    if not fut or fut.done():
        return JSONResponse({"ok": False, "error": "no such pending request"}, status_code=404)
    fut.set_result({
        "type": data.get("type", "text"),
        "content": data.get("content", ""),
        "tool_name": data.get("tool_name"),
        "tool_args": data.get("tool_args"),
    })
    return {"ok": True}


# Serve the web UI at "/". Declared last so /v1 and /api win the match.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")


BANNER = r"""
 _                                   _ _
| |__  _   _ _ __ ___   __ _ _ __   | | |_ __ ___
| '_ \| | | | '_ ` _ \ / _` | '_ \  | | | '_ ` _ \
| | | | |_| | | | | | | (_| | | | | | | | | | | | |
|_| |_|\__,_|_| |_| |_|\__,_|_| |_| |_|_|_| |_| |_|

  you are the model now  .  speaks OpenAI / Anthropic / Ollama
  UI + endpoints  ->  http://localhost:%d
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    try:
        print(BANNER % port)
    except Exception:
        print(f"human-llm  .  http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
