# agent_logic.py
# Псевдокод для демонстрации использования инструментов GaslessRelayTool в агенте SpoonOS

# Предположим, у нас есть агент, подключенный к MCP-серверу
# mcp_client = SpoonOSMCPClient("http://localhost:8000/mcp")

async def handle_user_transfer_request(user_intent: dict):
    """
    user_intent = {
        "from": "0x...",
        "to": "0x...",
        "asset": "NEO",
        "amount": 400000000, # 4.0 NEO
        "signature": "hex_str"
    }
    """
    # 1. Оценить стоимость комиссии
    gas_estimate_result = await mcp_client.call_tool(
        "estimate_gas_cost",
        params={
            "asset_symbol": user_intent["asset"],
            "fee_gas": 0.00012, # Пример фиксированной комиссии
            "intent_id": "uuid-123"
        }
    )
    fee_in_asset = gas_estimate_result["fee_in_asset"]

    # 2. Выполнить газлесс-трансфер
    execution_result = await mcp_client.call_tool(
        "execute_gasless_transfer",
        params={
            "from_addr": user_intent["from"],
            "to_addr": user_intent["to"],
            "asset_hash": "0xef4073a0f2b305a3d2a8c4e8b6d5c736c7c7c7c7", # NEO Hash
            "gross_amount": user_intent["amount"],
            "fee_in_asset": fee_in_asset,
            "user_signature": user_intent["signature"],
            "intent_id": "uuid-123"
        }
    )

    return execution_result