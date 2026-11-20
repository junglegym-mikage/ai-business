"""② 将来シミュレーションの再現用（仮定条件にもとづく試算。予測ではない）。

使い方: python3 sim_money.py [毎月の積立額] [年数]
毎月末に積立、月複利。運用手数料は利回りから差し引く。税金は売却時に利益へ課税した場合の例。
"""
import sys

FEE = 0.001        # 運用手数料（年）
INFLATION = 0.02   # 物価上昇率（年）
TAX = 0.20315      # 課税口座の譲渡益・配当等の税率（原則）
RATES = (-0.02, 0.0, 0.03, 0.05)


def future_value(monthly: int, years: int, rate: float, drop_last_year: float = 0.0) -> float:
    i = (rate - FEE) / 12
    months = years * 12
    balance = 0.0
    for k in range(months):
        in_last_year = k >= months - 12
        if drop_last_year and k == months - 12:
            balance *= 1 - drop_last_year
        growth = 0.0 if (drop_last_year and in_last_year) else i
        balance = balance * (1 + growth) + monthly
    return balance


def main() -> None:
    monthly = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    years = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    principal = monthly * years * 12
    print(f"元本 {principal:,}円（毎月{monthly:,}円×{years}年）")
    for r in RATES:
        b = future_value(monthly, years, r)
        print(f"想定利回り{r:+.0%}: 名目 {b:,.0f}円 / 実質 {b / (1 + INFLATION) ** years:,.0f}円")
    print(f"下落の例（最後の1年の初めに30%下落、その後横ばい）: {future_value(monthly, years, 0.05, 0.30):,.0f}円")
    b5 = future_value(monthly, years, 0.05)
    gain = b5 - principal
    print(f"課税口座で全額売却（5%ケース）: 利益 {gain:,.0f}円、税 {gain * TAX:,.0f}円")


if __name__ == "__main__":
    main()
