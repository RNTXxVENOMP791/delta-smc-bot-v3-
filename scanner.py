"""Scanner integration point for the next iteration.

The production scanner is intentionally not activated in this package.
Before unattended scanning is enabled, implement and test:
- separate native 3m, 5m and 15m candle retrieval,
- closed-candle timestamp alignment,
- SMC setup evaluation and one-signal-per-setup deduplication,
- signal freshness and invalidation checks,
- scanner health monitoring and Telegram alert throttling.
Do not generate live strategy alerts from the dummy-signal form in dashboard.py.
"""
