# NEO SpoonOS Gasless Relay Wibecoding Edition from Qwen-Coder

Этот проект реализует систему gasless-транзакций для NEO N3, интегрированную с SpoonOS через MCP. Пользователи могут выполнять транзакции (например, переводы NEO), не обладая собственным GAS, за счёт сжигания части отправляемого актива (NEO) для покрытия комиссии.

## Архитектура

- `config.py`: Конфигурация для подключения к NEO N3 и Flamingo API.
- `tools/gasless_relay.py`: Реализация основного инструмента SpoonOS.
- `contracts/GaslessRelay.cs`: Смарт-контракт на C# для выполнения операций.
- `tests/`: Unit-тесты для инструментов.
- `mcp_server.py`: MCP-сервер для предоставления инструментов SpoonOS-агентам.
- `requirements.txt`: Зависимости Python.
- `README.md`: Этот файл.

## Установка

1. Установите зависимости: `pip install -r requirements.txt`
2. Настройте `config.py` с вашими параметрами (WIF, адреса контрактов и т.д.).
3. Запустите MCP-сервер: `python mcp_server.py`

## Использование

SpoonOS-агент может вызывать инструменты `estimate_gas_cost` и `execute_gasless_transfer` через MCP-протокол.
