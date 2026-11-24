"""Headless demo of the Rack 07 workflow (no browser needed):  python demo_cli.py"""
import sys
from backend.seed import seed
from agent.mcp_hub import MCPHub
from agent.orchestrator import Agent
seed(); hub = MCPHub(); agent = Agent(hub)
for q in ["Which GPU rack is experiencing the greatest thermal stress?", "Why is Rack 07 overheating?"]:
    r = agent.handle(q)
    print("\n>>", q, "\n"); print(r["answer"]); print("\nMCP calls:", " -> ".join(f"{t['server']}.{t['tool']}" for t in r["trace"]))
    if r["kind"] == "investigation":
        ap = r["data"]["approval"]["approval_id"]
        print(f"\nOperator decision on {ap}:", hub.call("record_approved_action", {"approval_id": ap, "decision": "approved", "operator": "demo.operator"})["message"])
        print("Audit chain:", hub.call("verify_audit_chain"))
hub.close()
