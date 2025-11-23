import requests
from pydantic import BaseModel
from decimal import Decimal


class NeoNetworkConfig(BaseModel):
    rpc_url: str = "https://rpc.testnet.neo.org"
    flamingo_api: str = "https://api.flamingo.finance"
    relay_contract_hash: str = "0x1a2b3c...def"  # GaslessRelay
    agent_wallet_wif: str = "L4nZC5YBZ4PzU1JHb4YSDH25UyL8n8826hN297w2L7J8K9L9M9N9"  # приватный ключ агента (хранить в секрете!)
    min_agent_gas_balance: Decimal = Decimal("0.001")  # минимальный буфер GAS у агента
    slippage_bps: int = 50  # 0.5%


# This is a sample Python script.

# Press Ctrl+F5 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.


def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press F9 to toggle the breakpoint.


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('PyCharm')

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
