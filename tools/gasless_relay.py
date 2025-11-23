import asyncio
from typing import Dict, Any, Optional
from decimal import Decimal
import requests
from neo3.core import types
from neo3.wallet import account
from neo3.network import payloads
from neo3.api import noderpc
from neo3.contracts import vm as vm_builder
from neo3.crypto import signing
from neo3.contracts import contract
import json

class GaslessRelayTool:
    """
    MCP-совместимый инструмент для gasless transfers на NEO N3.
    Поддерживает оплату комиссии за счёт сжигания части отправляемых средств.
    """

    def __init__(self, config: 'NeoNetworkConfig'):
        self.config = config
        self.agent_acct = account.Account.from_wif(config.agent_wallet_wif)
        self.rpc_client = noderpc.NeoRpcClient(config.rpc_url)

    # ────────────────────────────────────────────────
    # MCP Tool: estimate_gas_cost
    # ────────────────────────────────────────────────
    async def estimate_gas_cost(
        self,
        asset_symbol: str = "NEO",
        fee_gas: float = 0.00012,
        intent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        MCP Tool Spec:
          name: "estimate_gas_cost"
          description: "Estimate fee in native asset (e.g. NEO) for gasless transfer"
          args:
            - asset_symbol: str (NEO, FLM, GAS, fUSD)
            - fee_gas: float (default 0.00012)
          returns: { "fee_in_asset": int, "asset_decimals": int, "burn_amount": int }
        """
        # 1. Получить курс через Flamingo API
        price = await self._get_price_from_flamingo(asset_symbol, "GAS")
        if price is None:
            raise RuntimeError("Failed to fetch price from Flamingo")

        # 2. Расчёт: fee_in_asset = fee_gas / price
        fee_in_asset = Decimal(str(fee_gas)) / Decimal(str(price))
        fee_in_asset += fee_in_asset * Decimal(self.config.slippage_bps) / 10000  # буфер

        # 3. Округлить до точности актива
        decimals = self._get_asset_decimals(asset_symbol)
        fee_raw = int(fee_in_asset * (10 ** decimals))

        return {
            "fee_in_asset": fee_raw,
            "asset_decimals": decimals,
            "burn_amount": fee_raw,
            "intent_id": intent_id,
            "source": "flamingo_oracle"
        }

    # ────────────────────────────────────────────────
    # MCP Tool: execute_gasless_transfer
    # ────────────────────────────────────────────────
    async def execute_gasless_transfer(
        self,
        from_addr: str,
        to_addr: str,
        asset_hash: str,
        gross_amount: int,          # например, 400_000_000 для 4 NEO
        fee_in_asset: int,          # из estimate_gas_cost
        user_signature: str,        # подпись пользователя на intent
        intent_id: str
    ) -> Dict[str, Any]:
        """
        MCP Tool Spec:
          name: "execute_gasless_transfer"
          description: "Execute transfer with fee covered by burning part of amount"
          args:
            - from_addr: str (sender)
            - to_addr: str (receiver)
            - asset_hash: str (e.g. NeoToken hash)
            - gross_amount: int
            - fee_in_asset: int
            - user_signature: hex str
            - intent_id: str
          returns: { "txid": str, "net_amount": int, "status": "sent" }
        """
        net_amount = gross_amount - fee_in_asset

        # 1. Проверить подпись пользователя
        intent_data = {
            "from": from_addr,
            "to": to_addr,
            "gross_amount": gross_amount,
            "fee_in_asset": fee_in_asset,
            "intent_id": intent_id
        }
        intent_json = json.dumps(intent_data, sort_keys=True)
        user_pubkey = signing.recover_public_key_from_signature(
            intent_json.encode(), bytes.fromhex(user_signature)
        )
        user_script_hash = contract.Contract.create_signature_redeem_script(user_pubkey).to_array()
        user_address = types.UInt160.deserialize_from_bytes(user_script_hash).to_address()

        if user_address != from_addr:
            raise ValueError("Invalid user signature for intent")

        # 2. Убедиться, что у агента есть GAS
        await self._ensure_agent_has_gas()

        # 3. Сформировать вызов контракта GaslessRelay
        script = await self._build_relay_script(
            from_addr=from_addr,
            to_addr=to_addr,
            asset_hash=asset_hash,
            net_amount=net_amount,
            burn_amount=fee_in_asset,
            intent_id=intent_id
        )

        # 4. Подготовить транзакцию
        tx = payloads.Transaction(
            version=0,
            nonce=12345,
            system_fee=120000,  # 0.0000012 GAS
            network_fee=100000, # 0.000001 GAS
            valid_until_block=999999,
            attributes=[],
            script=script,
            witnesses=[]
        )

        # 5. Подписать от имени агента (как witness)
        witness = await self._build_custom_witness(from_addr, self.config.relay_contract_hash)
        tx.witnesses = [witness]

        # 6. Подписать TX приватным ключом агента
        self.agent_acct.sign_tx(tx)

        # 7. Отправить
        txid = await self._send_raw_transaction(tx)
        return {
            "txid": txid,
            "net_amount": net_amount,
            "burn_amount": fee_in_asset,
            "status": "sent",
            "intent_id": intent_id
        }

    # ────────────────────────────────────────────────
    # Вспомогательные методы
    # ────────────────────────────────────────────────
    async def _get_price_from_flamingo(self, base: str, quote: str) -> Optional[float]:
        url = f"{self.config.flamingo_api}/price"
        try:
            resp = requests.get(url, params={"pair": f"{base}_{quote}"}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return float(data.get("price", 0))
        except Exception as e:
            print(f"⚠️ Flamingo price fetch failed: {e}")
            return None

    def _get_asset_decimals(self, symbol: str) -> int:
        # NEO/GAS: 8, FLM: 8, fUSD: 8
        return 8

    async def _ensure_agent_has_gas(self):
        """Если GAS < min — сделать swap FLM → GAS"""
        balance = await self._get_gas_balance(self.agent_acct.script_hash)
        if balance < self.config.min_agent_gas_balance:
            await self._swap_flm_to_gas(target_gas=Decimal("0.01"))

    async def _swap_flm_to_gas(self, target_gas: Decimal):
        # Пример запроса к Flamingo Swap API
        payload = {
            "fromToken": "FLM",
            "toToken": "GAS",
            "amount": str(int(target_gas * 100 * 10**8)),  # ~100 FLM
            "recipient": self.agent_acct.address
        }
        resp = requests.post(
            f"{self.config.flamingo_api}/swap",
            json=payload,
            headers={"Authorization": "Bearer YOUR_API_KEY"}
        )
        resp.raise_for_status()
        print("✅ Swap executed:", resp.json().get("tx"))

    async def _get_gas_balance(self, script_hash: types.UInt160) -> Decimal:
        # Запрос к RPC: invokefunction GasToken balanceOf
        # (реализация через neo3-python rpc client)
        try:
            result = await self.rpc_client.invoke_function(
                script_hash="0xd2a4cff31913016155e38e474a2c06d08be276cf",  # GAS Hash
                operation="balanceOf",
                args=[script_hash]
            )
            balance_raw = int.from_bytes(result.state, 'little')
            return Decimal(balance_raw) / 10**8
        except Exception as e:
            print(f"⚠️ RPC balance fetch failed: {e}")
            return Decimal(0)

    async def _build_relay_script(self, from_addr: str, to_addr: str, asset_hash: str, net_amount: int, burn_amount: int, intent_id: str) -> bytes:
        # Генерация script для вызова GaslessRelay.transferWithFeeFromAmount
        # через neo3.vm
        from neo3 import vm as vm_builder
        from neo3.core import types, cryptography

        # 1. Десериализуем адреса в UInt160
        from_script_hash = types.UInt160.from_string(from_addr)
        to_script_hash = types.UInt160.from_string(to_addr)
        asset_script_hash = types.UInt160.from_string(asset_hash)

        # 2. Собираем скрипт через vm_builder
        builder = vm_builder.ScriptBuilder()

        # 3. Пушим аргументы в обратном порядке (стек)
        builder.emit_push(intent_id.encode('utf-8'))      # string intent_id
        builder.emit_push(burn_amount)                    # long burn_amount
        builder.emit_push(net_amount)                     # long net_amount
        builder.emit_push(asset_script_hash)              # UInt160 asset_hash
        builder.emit_push(to_script_hash)                 # UInt160 to_addr
        builder.emit_push(from_script_hash)               # UInt160 from_addr

        # 4. SysCall: вызов метода контракта
        # System.Contract.Call(contract_hash, method, call_flags, args[])
        builder.emit_push(0x00)  # CallFlags.All (0x00)
        builder.emit_push(7)     # количество аргументов
        builder.emit(vm_builder.OpCode.PACK)  # упаковываем 7 аргументов в массив

        method_name = "transferWithFeeFromAmount"
        builder.emit_push(method_name.encode('utf-8'))

        contract_hash = types.UInt160.from_string(self.config.relay_contract_hash)
        builder.emit_push(contract_hash)

        builder.emit_syscall("System.Contract.Call")

        # 5. Получить итоговый байтовый скрипт
        return builder.to_array()

    async def _build_custom_witness(self, user_addr: str, contract_hash_str: str) -> payloads.Witness:
        # Создать witness с scope CustomContracts([contract_hash])
        # См. neo3/network/payloads/transaction.py
        # В NeoVM verification_script исполняется и должен вернуть true.
        # InvocationScript — исполняется перед verification_script.

        # Для CustomContracts:
        # - invocation_script: может быть пустым или содержать аргументы для verify
        # - verification_script: вызывает `GaslessRelay.verify(...)` и возвращает результат

        # Псевдокод verification_script:
        # PUSHDATA(intent_id)
        # PUSHDATA(signature)
        # PUSHDATA(user_addr)
        # PUSHDATA("verify")
        # PUSHDATA(GaslessRelay.Hash)
        # PUSHINT(0) // CallFlags
        # PUSH4 // num args
        # PACK
        # SYSCALL System.Contract.Call
        # ASSERT // результат должен быть true

        # Это сложный NeoVM-скрипт. Давайте сгенерируем его через vm_builder.

        builder = vm_builder.ScriptBuilder()

        # invocation_script: просто пушим подпись
        invocation_script_builder = vm_builder.ScriptBuilder()
        # invocation_script_builder.emit_push(user_signature_bytes) # Предполагаем, что подпись уже в стеке или передаётся отдельно

        # verification_script: вызов verify
        verification_script_builder = vm_builder.ScriptBuilder()
        verification_script_builder.emit_push(intent_id.encode('utf-8'))
        # signature будет из invocation_script -> берем с вершины стека
        verification_script_builder.emit(vm_builder.OpCode.DUP)  # копируем подпись
        verification_script_builder.emit_push(user_addr.encode('utf-8'))
        verification_script_builder.emit_push("verify".encode('utf-8'))
        verification_script_builder.emit_push(contract_hash_str.encode('utf-8'))
        verification_script_builder.emit_push(0)  # CallFlags
        verification_script_builder.emit_push(3)  # num args: user, sig, intent
        verification_script_builder.emit(vm_builder.OpCode.PACK)
        verification_script_builder.emit_syscall("System.Contract.Call")
        verification_script_builder.emit(vm_builder.OpCode.ASSERT)

        return payloads.Witness(
            invocation_script=invocation_script_builder.to_array(),
            verification_script=verification_script_builder.to_array()
        )

    async def _estimate_network_fee(self, tx: payloads.Transaction) -> int:
        # Использовать RPC: invokescript → estimate fees
        try:
            result = await self.rpc_client.invoke_script(tx.script)
            return result.gas_consumed
        except Exception as e:
            print(f"⚠️ Fee estimation failed: {e}")
            return 100000  # fallback

    async def _send_raw_transaction(self, tx: payloads.Transaction) -> str:
        # Отправка в RPC: sendrawtransaction
        raw_tx = tx.to_array().hex()
        try:
            result = await self.rpc_client.send_raw_transaction(raw_tx)
            return result
        except Exception as e:
            print(f"⚠️ TX send failed: {e}")
            raise