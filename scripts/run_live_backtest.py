#!/usr/bin/env python
"""
Executable script demonstrating how to backtest an Argo strategy.
Runs SuperTrendBreakoutStrategy over historical/synthetic market data.

Usage:
    python scripts/run_live_backtest.py
"""
import os
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

try:
    import django
    django.setup()
except Exception:
    pass

from argo.backtest.live_runner import LiveBacktestFacade, LiveBacktestConfig


def run():
    # 1. Define backtest configuration
    config = LiveBacktestConfig(
        strategy_class_path="argo.strategies.supertrend_breakout.SuperTrendBreakoutStrategy",
        strategy_name="SuperTrend Volatility Breakout",
        symbol="EUR/USD",
        venue="IDEALPRO",
        starting_balance=100_000.0,
        lookback_days=14,
        strategy_params={
            "atr_period": 14,
            "atr_multiplier": 3.0,
            "trade_size": 10_000.0,
            "min_adx": 22.0,
            "max_long_rsi": 75.0,
        },
    )

    # 2. Execute via Facade
    facade = LiveBacktestFacade(config=config)
    print(f"Starting live backtest simulation for {config.symbol}...")
    result = facade.execute()

    # 3. Print report
    facade.print_report(result)
    return result


if __name__ == "__main__":
    run()
