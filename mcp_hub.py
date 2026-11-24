"""MCP client hub: starts the five MCP servers as stdio subprocesses and routes tool calls to them.
Every call returns a trace entry so the UI can show exactly which MCP tools were used."""
import asyncio, json, sys, threading, time
from contextlib import AsyncExitStack
from pathlib import Path
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from backend.config import DB_PATH

SERVERS = {"thermal": "thermal_server.py", "compute": "compute_server.py", "maintenance": "maintenance_server.py",
           "resource": "resource_server.py", "approval": "approval_server.py"}
ROOT = Path(__file__).resolve().parent.parent

class MCPHub:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.sessions, self.tool_server, self.tools = {}, {}, {}
        self.ready = threading.Event(); self.error = None
        self.stack = None
        threading.Thread(target=self._run, daemon=True).start()
        self.ready.wait(60)
        if self.error: raise RuntimeError(self.error)

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start())
        self.loop.run_forever()

    async def _start(self):
        try:
            self.stack = AsyncExitStack()
            for name, script in SERVERS.items():
                params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_servers" / script)], cwd=str(ROOT),
                                         env={"GUARDIAN_DB": DB_PATH})   # servers must share the caller's database
                r, w = await self.stack.enter_async_context(stdio_client(params))
                s = await self.stack.enter_async_context(ClientSession(r, w))
                await s.initialize()
                self.sessions[name] = s
                for t in (await s.list_tools()).tools:
                    self.tool_server[t.name] = name
                    self.tools[t.name] = {"server": name, "description": t.description,
                                          "schema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)}
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self.ready.set()

    async def _call(self, tool, args):
        s = self.sessions[self.tool_server[tool]]
        res = await s.call_tool(tool, args)
        text = "".join(getattr(c, "text", "") for c in res.content)
        if getattr(res, "is_error", False) or getattr(res, "isError", False):
            return {"error": text or "tool error"}
        try: return json.loads(text)
        except Exception: return {"error": "tool returned non-JSON output", "raw": text[:300]}

    def call(self, tool, args=None, trace=None):
        args = {k: v for k, v in (args or {}).items() if v not in (None, "")}
        t0 = time.time()
        if tool not in self.tool_server:
            out = {"error": f"Tool {tool} is not available (MCP server down?)"}
        else:
            try: out = asyncio.run_coroutine_threadsafe(self._call(tool, args), self.loop).result(60)
            except Exception as e: out = {"error": f"MCP call failed: {type(e).__name__}: {e}"}
        entry = {"server": self.tool_server.get(tool, "?"), "tool": tool, "args": args, "ms": round((time.time() - t0) * 1000),
                 "status": "error" if isinstance(out, dict) and "error" in out else "ok"}
        if trace is not None: trace.append(entry)
        return out

    def close(self):
        async def _c(): await self.stack.aclose()
        try: asyncio.run_coroutine_threadsafe(_c(), self.loop).result(10)
        except Exception: pass
