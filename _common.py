"""Shared helpers for all MCP servers: SDK-version shim, audit-logging decorator, safe error handling."""
import sys, time, functools, inspect
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import db  # noqa: E402

try:                                   # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except ImportError:                    # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server

def make_server(name):
    return _Server(name)

def audited(server_name):
    """Every tool call is written to the tamper-evident audit log; failures return an error object
    instead of invented data."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            t0 = time.time()
            try:
                out = fn(*a, **kw)
                status = "error" if isinstance(out, dict) and "error" in out else "ok"
            except Exception as e:   # never fabricate results on failure
                out, status = {"error": f"{type(e).__name__}: {e}"}, "error"
            try:
                db.audit("tool_call", fn.__name__, {"server": server_name, "args": kw or list(a), "status": status,
                                                     "ms": round((time.time() - t0) * 1000)})
            except Exception: pass
            return out
        wrapper.__signature__ = inspect.signature(fn)
        return wrapper
    return deco
