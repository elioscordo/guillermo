from nautilus_trader.adapters.interactive_brokers.config import InteractiveBrokersDataClientConfig
from nautilus_trader.adapters.interactive_brokers.config import InteractiveBrokersExecClientConfig
from nautilus_trader.trading import TradingEngine

# Example for TWS paper trading (default port 7497)
data_config = InteractiveBrokersDataClientConfig(
    ibg_host="127.0.0.1",
    ibg_port=4002,
    ibg_client_id=1,
)

exec_config = InteractiveBrokersExecClientConfig(
    ibg_host="127.0.0.1",
    ibg_port=4002,
    ibg_client_id=1,
    account_id="DU123456",  # Your paper trading account ID
)

trading_engine = TradingEngine(data_config, exec_config) 