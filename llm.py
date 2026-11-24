"""OPTIONAL LLM mode (Anthropic Messages API via plain HTTPS - no extra SDK needed).
Enable with:  export ANTHROPIC_API_KEY=...   (optionally GUARDIAN_LLM_MODEL=claude-sonnet-5-5)
The model plans MCP tool calls and explains results; deterministic engines still do all scoring.
NOTE: this path needs internet + a key and was NOT exercised in the offline build environment;
the deterministic demo mode is the tested default and the automatic fallback."""
import json, os, urllib.request

class AnthropicLLM:
    def __init__(self, key, model=None):
        self.key, self.model = key, model or os.environ.get("GUARDIAN_LLM_MODEL", "claude-sonnet-5-5")

    def _post(self, body):
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
              headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r: return json.load(r)

    def run(self, hub, message, trace, system, max_steps=10):
        tools = [{"name": n, "description": t["description"] or n, "input_schema": t["schema"] or {"type": "object", "properties": {}}}
                 for n, t in hub.tools.items() if n not in ("record_approved_action",)]   # the agent may NOT record decisions
        msgs = [{"role": "user", "content": message}]
        data = {}
        for _ in range(max_steps):
            resp = self._post({"model": self.model, "max_tokens": 1500, "system": system, "tools": tools, "messages": msgs})
            msgs.append({"role": "assistant", "content": resp["content"]})
            calls = [b for b in resp["content"] if b["type"] == "tool_use"]
            if not calls:
                text = "".join(b.get("text", "") for b in resp["content"] if b["type"] == "text")
                return {"answer": text, "kind": "llm", "data": data, "trace": trace, "mode": f"llm ({self.model})"}
            results = []
            for b in calls:
                out = hub.call(b["name"], b["input"], trace)
                data[b["name"]] = out
                results.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(out)[:12000]})
            msgs.append({"role": "user", "content": results})
        raise RuntimeError("LLM exceeded max tool steps")

def from_env():
    k = os.environ.get("ANTHROPIC_API_KEY")
    return AnthropicLLM(k) if k else None
