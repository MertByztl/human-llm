"""STRIX-JR - a tiny Strix-style autonomous agent that uses human-llm as its brain.

It fires OpenAI-style requests at a running human-llm server; YOU answer them in
the web UI. No Docker, no API key, no model. The "intelligence" is the human.

Usage:
    # 1. start the server in another terminal:  python server.py
    # 2. then run this:
    python examples/demo_agent.py
    # optional: point somewhere else / change step count
    HUMAN_LLM_URL=http://localhost:8000 python examples/demo_agent.py --steps 5
"""
import argparse
import json
import os
import sys
import urllib.request

BASE = os.environ.get("HUMAN_LLM_URL", "http://localhost:8000").rstrip("/")
ENDPOINT = BASE + "/v1/chat/completions"


def ask(messages):
    body = {"model": "human-llm", "messages": messages}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=data,
        headers={"Content-Type": "application/json", "Authorization": "Bearer strix-jr"},
    )
    with urllib.request.urlopen(req, timeout=3600) as r:  # waits for the human
        return json.loads(r.read().decode("utf-8"))


BANNER = r"""
  ___ _____ ___ _____  __    _ ___
 / __|_   _| _ \_ _\ \/ /___| | _ \
 \__ \ | | |   /| | >  <___| |   /
 |___/ |_| |_|_\___/_/\_\   |_|_|_\   STRIX-JR
        autonomous pentest agent  .  brain = you (human-llm)
"""

TASK = ("Target: http://demo.local  (authorized practice lab).\n"
        "Goal: suggest ONE next action to probe it for a vulnerability.\n"
        "You are the reasoning core driving this agent. Give the single next step.")


def main():
    parser = argparse.ArgumentParser(description="STRIX-JR demo agent for human-llm")
    parser.add_argument("--steps", type=int, default=3, help="how many turns to run")
    args = parser.parse_args()

    print(BANNER)
    print(f"[STRIX-JR] brain endpoint: {ENDPOINT}")
    sys.stdout.flush()

    messages = [
        {"role": "system",
         "content": "You are the reasoning core of STRIX-JR, an autonomous "
                    "penetration-testing agent. For each turn, reply with the single "
                    "next action the agent should take. Be concise, like a hacker."},
        {"role": "user", "content": TASK},
    ]

    for step in range(1, args.steps + 1):
        print(f"\n[STRIX-JR] step {step} -> asking the model (that's YOU in the UI)...")
        print("[STRIX-JR] waiting for the brain to respond...")
        sys.stdout.flush()

        resp = ask(messages)
        msg = resp["choices"][0]["message"]
        content = msg.get("content") or json.dumps(msg.get("tool_calls"))

        print(f"[MODEL -> AGENT] {content}")
        print(f"[STRIX-JR] executing step {step}... (simulated) done.")
        sys.stdout.flush()

        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user",
                         "content": f"Result of step {step}: (simulated) OK. "
                                    f"What's the next action for step {step + 1}?"})

    print("\n[STRIX-JR] run complete. A human was the brain the whole time. hahaha. 🧠")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
