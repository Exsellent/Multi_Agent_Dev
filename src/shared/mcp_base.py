import inspect
import json
import logging
import os

from fastapi import FastAPI, Request
from pydantic import BaseModel, ValidationError

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)


class MCPRequest(BaseModel):
    method: str
    params: dict
    id: int | None = None


class MCPAgent:
    def __init__(self, name: str):
        self.name = name
        self.app = FastAPI()
        self.tools = {}

        @self.app.get("/health")
        def health():
            return {"status": "ok", "agent": self.name}

        @self.app.post("/mcp")
        async def mcp(request: Request):

            try:
                # Получаем raw body
                body = await request.body()

                # Parsim JSON
                data = json.loads(body.decode('utf-8'))

                # Validating via Pydantic
                req = MCPRequest(**data)

            except json.JSONDecodeError as e:
                return {
                    "error": "Invalid JSON",
                    "details": str(e),
                    "hint": "Send valid JSON with 'method' and 'params'"
                }
            except ValidationError as e:
                return {
                    "error": "Invalid MCP request format",
                    "details": str(e),
                    "hint": "Required fields: method (str), params (dict)"
                }
            except Exception as e:
                return {
                    "error": "Request processing failed",
                    "details": str(e)
                }

            # Processing the MCP methoda
            tool_name = req.method.replace("tools/", "")

            if tool_name not in self.tools:
                return {
                    "error": f"Unknown tool: {tool_name}",
                    "available_tools": list(self.tools.keys())
                }

            handler = self.tools[tool_name]

            try:
                if inspect.iscoroutinefunction(handler):
                    return await handler(**req.params)
                else:
                    return handler(**req.params)
            except TypeError as e:
                return {
                    "error": f"Invalid parameters for tool '{tool_name}'",
                    "details": str(e)
                }
            except Exception as e:
                return {
                    "error": f"Tool execution failed",
                    "tool": tool_name,
                    "details": str(e)
                }

    def register_tool(self, name: str, handler):
        self.tools[name] = handler
        logging.getLogger(self.name).info(f"Registered tool: {name}")
