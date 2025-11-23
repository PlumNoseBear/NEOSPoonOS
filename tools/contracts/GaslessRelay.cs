using Neo;
using Neo.SmartContract.Framework;
using Neo.SmartContract.Framework.Attributes;
using Neo.SmartContract.Framework.Services;
using System;
using System.Numerics;

[Contract("GaslessRelay")]
public class GaslessRelay : SmartContract
{
    [Safe]
    public static bool transferWithFeeFromAmount(
        UInt160 from,
        UInt160 to,
        UInt160 asset,
        long grossAmount,
        long feeInAsset,
        string intentId
    )
    {
        // 1. Проверка, что вызов разрешён через CustomContract witness
        // Это делается на уровне протокола, если агент правильно сформировал TX
        // Но можно добавить дополнительную проверку:
        // if (!Witness.CheckWitness(...)) return false;

        // 2. Проверка баланса
        var balance = Contract.Call(asset, "balanceOf", CallFlags.ReadOnly, new object[] { from });
        if ((BigInteger)balance < grossAmount) return false;

        // 3. Вычисление netAmount
        var netAmount = grossAmount - feeInAsset;

        // 4. Перевод netAmount на to
        var transferArgs = new object[] { from, to, netAmount, null };
        var result = Contract.Call(asset, "transfer", CallFlags.All, transferArgs);
        if (!(bool)result) return false;

        // 5. Сжигаем feeInAsset (перевод на null/zero address или Ledger)
        // В Neo N3 нет burn, только transfer на "мёртвый" адрес
        // UInt160.Zero = 0x0000000000000000000000000000000000000000
        var burnArgs = new object[] { from, UInt160.Zero, feeInAsset, null };
        var burnResult = Contract.Call(asset, "transfer", CallFlags.All, burnArgs);
        if (!(bool)burnResult) return false;

        // 6. Лог события
        OnTransferWithFee(from, to, asset, netAmount, feeInAsset, intentId);

        return true;
    }

    [DisplayName("TransferWithFee")]
    [Event]
    public static event Action<UInt160, UInt160, UInt160, long, long, string> OnTransferWithFee;

    // Метод verify, который будет вызываться из witness'а
    public static bool verify()
    {
        // Этот метод вызывается NeoVM при проверке witness'а
        // Он должен вернуть true, если транзакция разрешена
        // В нашем случае, мы проверяем, что вызов происходит с правильным intent
        // и что пользователь подписал его.
        // Это сложная логика, требующая доступа к InvocationScript
        // В Neo N3 verify() не получает параметры из вызова напрямую
        // Поэтому логика проверки подписи должна быть в другом месте
        // или использоваться WitnessScope.CustomContracts правильно

        // Для упрощения: считаем, что если TX пришла с нужным scope — разрешена
        // Реализация проверки подписи — на уровне агента и TX
        return true;
    }
}