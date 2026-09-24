from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide, TimeInForce

from argo.strategies.base import ArgoBaseStrategy


class MACDStrategyConfig(StrategyConfig, frozen=True):
    """
    Configuration for Moving Average Convergence Divergence (MACD) Strategy.
    """
    instrument_id: str
    bar_type: str
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    trade_size: float = 100.0


class MACDStrategy(ArgoBaseStrategy):
    """
    MACD Momentum Strategy:
    - Buys on bullish MACD line crossover above signal line.
    - Closes on bearish MACD line crossover below signal line.
    """

    def __init__(self, config: MACDStrategyConfig):
        super().__init__(config=config)
        self.fast_ema: float | None = None
        self.slow_ema: float | None = None
        self.signal_ema: float | None = None
        self.last_macd: float | None = None
        self.last_signal: float | None = None
        self.position_open = False

    def on_start(self):
        super().on_start()

    def on_bar(self, bar: Bar):
        if not self.is_matching_bar(bar):
            return

        close = float(bar.close)
        k_fast = 2.0 / (self.config.fast_period + 1)
        k_slow = 2.0 / (self.config.slow_period + 1)
        k_signal = 2.0 / (self.config.signal_period + 1)

        self.fast_ema = close if self.fast_ema is None else (close * k_fast) + (self.fast_ema * (1 - k_fast))
        self.slow_ema = close if self.slow_ema is None else (close * k_slow) + (self.slow_ema * (1 - k_slow))

        macd_line = self.fast_ema - self.slow_ema
        self.signal_ema = macd_line if self.signal_ema is None else (macd_line * k_signal) + (self.signal_ema * (1 - k_signal))

        if self.last_macd is not None and self.last_signal is not None:
            # Bullish crossover
            if self.last_macd <= self.last_signal and macd_line > self.signal_ema:
                if not self.position_open:
                    self.log.info(f"[{self.instrument_id}] MACD Bullish Crossover. Going long.")
                    qty = self.make_qty(self.config.trade_size)
                    order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.FOK)
                    self.submit_order(order)
                    self.position_open = True
            # Bearish crossover
            elif self.last_macd >= self.last_signal and macd_line < self.signal_ema:
                if self.position_open:
                    self.log.info(f"[{self.instrument_id}] MACD Bearish Crossover. Closing long.")
                    qty = self.make_qty(self.config.trade_size)
                    order = self.order_factory.market(self.instrument_id, OrderSide.SELL, qty, TimeInForce.FOK)
                    self.submit_order(order)
                    self.position_open = False

        self.last_macd = macd_line
        self.last_signal = self.signal_ema

    def on_stop(self):
        self.log.info(f"Stopping MACDStrategy for {self.instrument_id}")
