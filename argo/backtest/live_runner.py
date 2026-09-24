import datetime
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from argo.backtest.results import BacktestResult
from argo.backtest.runner import StrategyBacktestRunner


@dataclass
class LiveBacktestConfig:
    """Configuration Value Object for live strategy backtest simulation."""
    strategy_class_path: str = "argo.strategies.supertrend_breakout.SuperTrendBreakoutStrategy"
    strategy_name: str = "SuperTrend Volatility Breakout"
    symbol: str = "EUR/USD"
    venue: str = "IDEALPRO"
    asset_class: str = "FX"
    currency: str = "USD"
    price_precision: int = 5
    price_increment: float = 0.00001
    lot_size: float = 1.0
    size_precision: int = 0
    multiplier: float = 1.0
    starting_balance: float = 100_000.0
    lookback_days: int = 7
    bar_type_spec: str = "1-MINUTE-MID-EXTERNAL"
    strategy_params: Dict[str, Any] = field(default_factory=lambda: {
        "atr_period": 14,
        "atr_multiplier": 3.0,
        "trade_size": 1000.0,
        "min_adx": 22.0,
        "max_long_rsi": 75.0,
    })


class BacktestMockInstanceFactory:
    """Factory creating transient instances compatible with StrategyBacktestRunner."""

    @staticmethod
    def create(cfg: LiveBacktestConfig):
        class _Model:
            class_path = cfg.strategy_class_path
            name = cfg.strategy_name

        class _Instrument:
            symbol = cfg.symbol
            venue = cfg.venue
            asset_class = cfg.asset_class
            currency = cfg.currency
            price_precision = cfg.price_precision
            price_increment = cfg.price_increment
            multiplier = cfg.multiplier
            lot_size = cfg.lot_size
            size_precision = cfg.size_precision
            ib_contract = None

            @property
            def instrument_id_str(self) -> str:
                return f"{self.symbol}.{self.venue}"

        class _Instance:
            id = 999
            strategy_model = _Model()
            instrument = _Instrument()
            params = {**cfg.strategy_params, "bar_type": f"{_Instrument().instrument_id_str}-{cfg.bar_type_spec}"}

        return _Instance()


class LiveBacktestFacade:
    """
    Facade orchestrating live/historical backtesting sessions for NautilusTrader strategies.
    Uses fallback data chain (catalog -> IB Gateway -> synthetic generation).
    """

    def __init__(self, config: Optional[LiveBacktestConfig] = None):
        self.config = config or LiveBacktestConfig()
        self.runner = StrategyBacktestRunner(starting_balance=self.config.starting_balance)

    def execute(self) -> BacktestResult:
        """Executes the backtest session and returns metrics."""
        instance = BacktestMockInstanceFactory.create(self.config)
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now - datetime.timedelta(days=self.config.lookback_days)
        return self.runner.run(instance, start=start, end=now)

    def print_report(self, result: BacktestResult) -> None:
        """Formats and logs a performance summary report."""
        sep = "=" * 64
        print(f"\n{sep}")
        print(f" LIVE BACKTEST REPORT: {result.strategy_name}")
        print(f" Instrument: {result.instrument_id} | Period: {result.start_time} -> {result.end_time}")
        print(sep)
        print(f" Initial Capital : ${result.initial_capital:,.2f}")
        print(f" Final Equity    : ${result.final_equity:,.2f}")
        print(f" Total Net PnL   : ${result.total_pnl:,.2f} ({result.return_pct:.2%})")
        print(f" Sharpe Ratio    : {result.sharpe_ratio:.2f}")
        print(f" Sortino Ratio   : {result.sortino_ratio:.2f}")
        print(f" Max Drawdown    : {result.max_drawdown_pct:.2%}")
        print(f" Total Trades    : {result.total_trades} (Win Rate: {result.win_rate:.1%})")
        print(f" Winning / Losing: {result.winning_trades} wins / {result.losing_trades} losses")
        print(f"{sep}\n")
