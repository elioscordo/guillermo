from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide, TimeInForce

from argo.strategies.base import ArgoBaseStrategy


class BuyAndHoldConfig(StrategyConfig, frozen=True):
    """
    Configuration for baseline Buy and Hold benchmark strategy.
    """
    instrument_id: str
    bar_type: str
    trade_size: float = 100.0


class BuyAndHoldStrategy(ArgoBaseStrategy):
    """
    Buy and Hold Strategy:
    - Buys on the very first received bar and holds until strategy stops.
    - Used as a benchmark baseline against all active alpha strategies.
    """

    def __init__(self, config: BuyAndHoldConfig):
        super().__init__(config=config)
        self.position_open = False

    def on_start(self):
        super().on_start()

    def on_bar(self, bar: Bar):
        if not self.is_matching_bar(bar):
            return

        if not self.position_open:
            self.log.info(f"[{self.instrument_id}] Initial Buy and Hold entry at {bar.close}.")
            qty = self.make_qty(self.config.trade_size)
            order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.GTC)
            self.submit_order(order)
            self.position_open = True

    def on_stop(self):
        self.log.info(f"Stopping BuyAndHoldStrategy for {self.instrument_id}")
