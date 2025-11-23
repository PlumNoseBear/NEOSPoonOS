import asyncio
from typing import Dict, Any
from pydantic import BaseModel
from fastmcp import FastMCP
from fastmcp.transport import HTTPTransport
from fastmcp.types import ToolCall, ToolResponse
from config import NeoNetworkConfig
from tools.gasless_relay import GaslessRelayTool

async def main():
    config = NeoNetworkConfig(
        # ... ваша конфигурация
    )
    tool_instance = GaslessRelayTool(config)

    mcp = FastMCP(
        name="NEO Gasless Relay MCP",
        description="MCP server for gasless NEO transfers",
        version="0.1.0"
    )

    @mcp.tool(
        name="estimate_gas_cost",
        description="Estimate fee in native asset (e.g. NEO) for gasless transfer",
        parameters={
            "type": "object",
            "properties": {
                "asset_symbol": {"type": "string", "default": "NEO"},
                "fee_gas": {"type": "number", "default": 0.00012},
                "intent_id": {"type": "string", "nullable": True}
            },
            "required": []
        }
    )
    async def estimate_gas_cost_tool(params: Dict[str, Any]) -> ToolResponse:
        result = await tool_instance.estimate_gas_cost(
            asset_symbol=params.get("asset_symbol", "NEO"),
            fee_gas=params.get("fee_gas", 0.00012),
            intent_id=params.get("intent_id")
        )
        return ToolResponse(content=result)

    @mcp.tool(
        name="execute_gasless_transfer",
        description="Execute transfer with fee covered by burning part of amount",
        parameters={
            "type": "object",
            "properties": {
                "from_addr": {"type": "string"},
                "to_addr": {"type": "string"},
                "asset_hash": {"type": "string"},
                "gross_amount": {"type": "integer"},
                "fee_in_asset": {"type": "integer"},
                "user_signature": {"type": "string"},
                "intent_id": {"type": "string"}
            },
            "required": ["from_addr", "to_addr", "asset_hash", "gross_amount", "fee_in_asset", "user_signature", "intent_id"]
        }
    )
    async def execute_gasless_transfer_tool(params: Dict[str, Any]) -> ToolResponse:
        result = await tool_instance.execute_gasless_transfer(
            from_addr=params["from_addr"],
            to_addr=params["to_addr"],
            asset_hash=params["asset_hash"],
            gross_amount=params["gross_amount"],
            fee_in_asset=params["fee_in_asset"],
            user_signature=params["user_signature"],
            intent_id=params["intent_id"]
        )
        return ToolResponse(content=result)

    transport = HTTPTransport(
        host="0.0.0.0",
        port=8000,
        path="/mcp"
    )
    await mcp.start(transport)

if __name__ == "__main__":
    asyncio.run(main())