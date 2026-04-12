
from decimal import Decimal

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import FillModel
from nautilus_trader.backtest.modules import FXRolloverInterestConfig
from nautilus_trader.backtest.modules import FXRolloverInterestModule
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import RiskEngineConfig
from nautilus_trader.examples.strategies.ema_cross import EMACross
from nautilus_trader.examples.strategies.ema_cross import EMACrossConfig
from nautilus_trader.model import BarType
from nautilus_trader.model import Money
from nautilus_trader.model import Venue
from nautilus_trader.model.currencies import JPY
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.persistence.wranglers import QuoteTickDataWrangler
from nautilus_trader.test_kit.providers import TestDataProvider
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.adapters.interactive_brokers.common import IBContract

from nautilus_trader.adapters.interactive_brokers.historical.client import HistoricInteractiveBrokersClient
from ibapi.common import MarketDataTypeEnum


async def getHistoricClient():
    # Initialize the client
    client = HistoricInteractiveBrokersClient(
        host="127.0.0.1",
        port=7497,
        client_id=1,
        market_data_type=MarketDataTypeEnum.DELAYED_FROZEN,  # Use delayed data if no subscription
        log_level="INFO"
    )

    # Connect to TWS/Gateway
    await client.connect()

# Define contracts
contracts = [
    IBContract(secType="STK", symbol="AAPL", exchange="SMART", primaryExchange="NASDAQ"),
    IBContract(secType="STK", symbol="MSFT", exchange="SMART", primaryExchange="NASDAQ"),
    IBContract(secType="CASH", symbol="EUR", currency="USD", exchange="IDEALPRO"),
]
# Initialize a backtest configuration
config = BacktestEngineConfig(
    trader_id="BACKTESTER-001",
    logging=LoggingConfig(log_level="ERROR"),
    risk_engine=RiskEngineConfig(
        bypass=True,  # Example of bypassing pre-trade risk checks for backtests
    ),
)

# Build backtest engine
engine = BacktestEngine(config=config)

