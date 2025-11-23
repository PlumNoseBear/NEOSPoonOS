import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from tools.gasless_relay import GaslessRelayTool
from config import NeoNetworkConfig


@pytest.fixture
def config():
    return NeoNetworkConfig(
        rpc_url="https://testnet-rpc.neo.org",
        flamingo_api="https://api.flamingo.finance",
        relay_contract_hash="0x1a2b3c...",
        agent_wallet_wif="L4nZC5YBZ4PzU1JHb4YSDH25UyL8n8826hN297w2L7J8K9L9M9N9",
        min_agent_gas_balance=Decimal("0.001"),
        slippage_bps=50
    )


@pytest.fixture
def tool(config):
    return GaslessRelayTool(config)


class TestGaslessRelayTool:

    @pytest.mark.parametrize("base,quote,expected_price", [
        ("NEO", "GAS", 42.7),
        ("FLM", "GAS", 0.3),
    ])
    def test_get_price_from_flamingo(self, tool, base, quote, expected_price):
        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"price": expected_price}
            mock_get.return_value.raise_for_status.return_value = None

            price = tool._get_price_from_flamingo(base, quote)
            assert price == expected_price

    def test_estimate_gas_cost(self, tool):
        with patch.object(tool, '_get_price_from_flamingo', return_value=42.7):
            result = tool.estimate_gas_cost(asset_symbol="NEO", fee_gas=0.00012)
            assert "fee_in_asset" in result
            assert result["fee_in_asset"] > 0
            assert result["asset_decimals"] == 8

    def test_get_gas_balance(self, tool):
        mock_script_hash = MagicMock()
        with patch.object(tool.rpc_client, 'invoke_function') as mock_invoke:
            mock_invoke.return_value.state = (int(Decimal("0.001") * 10**8)).to_bytes(8, 'little')
            balance = tool._get_gas_balance(mock_script_hash)
            assert balance == Decimal("0.001")

    def test_ensure_agent_has_gas_enough(self, tool):
        with patch.object(tool, '_get_gas_balance', return_value=Decimal("0.002")):
            # Should not call swap
            with patch.object(tool, '_swap_flm_to_gas') as mock_swap:
                tool._ensure_agent_has_gas()
                mock_swap.assert_not_called()

    def test_ensure_agent_has_gas_insufficient(self, tool):
        with patch.object(tool, '_get_gas_balance', return_value=Decimal("0.0005")):
            # Should call swap
            with patch.object(tool, '_swap_flm_to_gas') as mock_swap:
                tool._ensure_agent_has_gas()
                mock_swap.assert_called_once()

    def test_build_relay_script(self, tool):
        script = tool._build_relay_script(
            from_addr="0xAb4b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
            to_addr="0x1234567890123456789012345678901234567890",
            asset_hash="0xef4073a0f2b305a3d2a8c4e8b6d5c736c7c7c7c7",
            net_amount=399_999_659,
            burn_amount=341,
            intent_id="uuid-123"
        )
        # Проверим, что скрипт не пустой
        assert len(script) > 0
        # Проверим, что в скрипте есть вызов System.Contract.Call
        # (это сложнее проверить без парсинга NeoVM, но можно проверить на наличие байтов вызова)
        # Например, 0x62 — это OpCode для SYSCALL
        assert 0x62 in script

    def test_build_custom_witness(self, tool):
        witness = tool._build_custom_witness(
            user_addr="0xAb4b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
            contract_hash_str="0x1a2b3c..."
        )
        # Проверим, что witness не None
        assert witness is not None
        # Проверим, что verification_script не пустой
        assert len(witness.verification_script) > 0
        # Проверим, что invocation_script может быть пустым (это нормально)
        # assert len(witness.invocation_script) > 0 # Необязательно

    def test_execute_gasless_transfer_success(self, tool):
        # Подготовка
        from_addr = "0xAb4b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"
        to_addr = "0x1234567890123456789012345678901234567890"
        asset_hash = "0xef4073a0f2b305a3d2a8c4e8b6d5c736c7c7c7c7"
        gross_amount = 400_000_000
        fee_in_asset = 341
        user_signature = "a1b2c3d4e5f6..."
        intent_id = "uuid-123"

        with patch.object(tool, 'estimate_gas_cost', return_value={"fee_in_asset": fee_in_asset}):
            with patch.object(tool, '_ensure_agent_has_gas'):
                with patch.object(tool, '_build_relay_script', return_value=b'\x00' * 20):
                    with patch.object(tool, '_build_custom_witness', return_value=MagicMock()):
                        with patch.object(tool.agent_acct, 'sign_tx'):
                            with patch.object(tool, '_send_raw_transaction', return_value="0xdeadbeef"):
                                # Вызов
                                result = tool.execute_gasless_transfer(
                                    from_addr=from_addr,
                                    to_addr=to_addr,
                                    asset_hash=asset_hash,
                                    gross_amount=gross_amount,
                                    fee_in_asset=fee_in_asset,
                                    user_signature=user_signature,
                                    intent_id=intent_id
                                )
                                # Проверка
                                assert result["status"] == "sent"
                                assert result["net_amount"] == gross_amount - fee_in_asset
                                assert result["txid"] == "0xdeadbeef"

    def test_execute_gasless_transfer_invalid_signature(self, tool):
        with patch("neo3.crypto.signing.recover_public_key_from_signature", side_effect=ValueError):
            with pytest.raises(ValueError):
                tool.execute_gasless_transfer(
                    from_addr="0xAb4b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
                    to_addr="0x1234567890123456789012345678901234567890",
                    asset_hash="0xef...",
                    gross_amount=400_000_000,
                    fee_in_asset=341,
                    user_signature="invalid",
                    intent_id="uuid-123"
                )
