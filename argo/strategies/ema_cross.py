from dataclasses import dataclass, field
import json
import redis

from nautilus_trader.common.actor import Actor
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce

from argo.strategies.base import ArgoBaseStrategy


class EMACrossStrategyConfig(StrategyConfig, frozen=True):
    """
    Configuration for the EMACrossStrategy.
    """
    instrument_id: str
    bar_type: str
    fast_ema_period: int = 10
    slow_ema_period: int = 20
    trade_size: float = 100.0
    redis_host: str = "localhost"
    redis_port: int = 6379


class EMACrossStrategy(ArgoBaseStrategy):
    """
    A simple EMA cross strategy that goes long when the fast EMA crosses above
    the slow EMA, and closes the position when the fast EMA crosses below the slow EMA.
    """

    def __init__(self, config: EMACrossStrategyConfig):
        super().__init__(config=config)
        self.fast_ema = None
        self.slow_ema = None
        self.last_fast_ema = None
        self.last_slow_ema = None
        self.position_open = False

    def on_start(self):
        super().on_start()
        self.log.info(
            f"Configured fast_ema={self.config.fast_ema_period}, slow_ema={self.config.slow_ema_period}"
        )
        
        # Fire Redis Pub/Sub start event
        try:
            r = redis.Redis(host=self.config.redis_host, port=self.config.redis_port, db=0)
            event_data = {
                "event": "strategy_started",
                "strategy": self.__class__.__name__,
                "instrument_id": str(self.instrument_id),
            }
            r.publish("nautilus_events", json.dumps(event_data))
            self.log.info("Fired start event to Redis Pub/Sub")
        except Exception as e:
            self.log.error(f"Failed to publish start event to Redis: {e}")

    def on_bar(self, bar: Bar):
        if not self.is_matching_bar(bar):
            return

        # Calculate EMAs (simplified for example, a real strategy would use an indicator library)
        if self.fast_ema is None:
            self.fast_ema = bar.close
            self.slow_ema = bar.close
        else:
            self.last_fast_ema = self.fast_ema
            self.last_slow_ema = self.slow_ema
            self.fast_ema = (bar.close * (2 / (self.config.fast_ema_period + 1))) + (self.fast_ema * (1 - (2 / (self.config.fast_ema_period + 1))))
            self.slow_ema = (bar.close * (2 / (self.config.slow_ema_period + 1))) + (self.slow_ema * (1 - (2 / (self.config.slow_ema_period + 1))))

        if self.last_fast_ema is None or self.last_slow_ema is None:
            return  # Not enough data yet

        # Check for cross
        if self.fast_ema > self.slow_ema and self.last_fast_ema <= self.last_slow_ema:
            if not self.position_open:
                self.log.info(f"[{self.instrument_id}] Bullish cross detected. Going long.")
                qty = self.make_qty(self.config.trade_size)
                order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.FOK)
                self.submit_order(order)
                self.position_open = True
        elif self.fast_ema < self.slow_ema and self.last_fast_ema >= self.last_slow_ema:
            if self.position_open:
                self.log.info(f"[{self.instrument_id}] Bearish cross detected. Closing long position.")
                qty = self.make_qty(self.config.trade_size)
                order = self.order_factory.market(self.instrument_id, OrderSide.SELL, qty, TimeInForce.FOK)
                self.submit_order(order)
                self.position_open = False

    def on_stop(self):
        self.log.info(f"Stopping EMACrossStrategy for {self.instrument_id}")