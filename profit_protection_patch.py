from pathlib import Path

SCANNER = Path("scanner.py")

OLD_LEVELS = '''TRAIL_LEVELS = [
    (10.0, 7.0),
    (20.0, 6.0),
    (30.0, 5.0),
    (50.0, 4.0),
    (75.0, 3.5),
    (100.0, 3.0),
    (150.0, 2.5),
    (200.0, 2.0),
    (300.0, 1.5),
]'''

NEW_LEVELS = '''TRAIL_LEVELS = [
    # Peak kâra gÃ¶re kÃ¢r koruma: geri verme artÄ±k sabit ve Ã§ok dar deÄŸil.
    # Ã–rnek: +300% peak -> en az yaklaÅŸÄ±k +180% korunur.
    (10.0, 7.0),
    (20.0, 8.0),
    (30.0, 10.0),
    (50.0, 20.0),
    (75.0, 30.0),
    (100.0, 40.0),
    (150.0, 60.0),
    (200.0, 80.0),
    (300.0, 120.0),
]'''

OLD_CLOSE = '''            if exit_reason:

                close_paper_trade(
                    trade,
                    current_price,
                    profit_pct,
                    profit_tl,
                    exit_reason,
                )'''

NEW_CLOSE = '''            if exit_reason:

                # Trailing stop periyodik taramalarda atlanabilir.
                # Stop seviyesi aÅŸÄ±ldÄ±ysa paper iÅŸlemi mevcut fiyatla
                # deÄŸil, stop seviyesine yakÄ±n simÃ¼le eder. BÃ¶ylece
                # +300% -> +78% gibi sahte bÃ¼yÃ¼k geri verme kaydÄ± oluÅŸmaz.
                exit_price = current_price

                if exit_reason == "TRAILING_STOP":
                    allowed_drawdown = get_trailing_drawdown(
                        peak_profit_pct
                    )
                    stop_profit_pct = (
                        peak_profit_pct
                        - allowed_drawdown
                    )

                    trailing_stop_price = (
                        entry_price
                        * (1 + stop_profit_pct / 100)
                    )

                    if current_price <= trailing_stop_price:
                        exit_price = trailing_stop_price

                exit_profit_pct = (
                    (exit_price / entry_price) - 1
                ) * 100

                exit_profit_tl = (
                    STAKE_TL
                    * exit_profit_pct
                    / 100
                )

                close_paper_trade(
                    trade,
                    exit_price,
                    exit_profit_pct,
                    exit_profit_tl,
                    exit_reason,
                )'''

text = SCANNER.read_text(encoding="utf-8")

if OLD_LEVELS not in text:
    raise SystemExit("Beklenen TRAIL_LEVELS bloÄŸu bulunamadÄ±; patch uygulanmadÄ±.")

if OLD_CLOSE not in text:
    raise SystemExit("Beklenen trailing kapanÄ±ÅŸ bloÄŸu bulunamadÄ±; patch uygulanmadÄ±.")

text = text.replace(OLD_LEVELS, NEW_LEVELS, 1)
text = text.replace(OLD_CLOSE, NEW_CLOSE, 1)
SCANNER.write_text(text, encoding="utf-8")
print("Profit protection patch uygulandÄ±.")
