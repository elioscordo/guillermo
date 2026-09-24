import importlib
import inspect
import pkgutil
from django.apps import apps
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarType
from nautilus_trader.trading.strategy import Strategy as NautilusStrategy

DEFAULT_STRATEGIES = [
    {
        "name": "EMA Crossover Strategy",
        "class_path": "argo.strategies.ema_cross.EMACrossStrategy",
        "description": "Trend-following strategy using Fast vs Slow Exponential Moving Average crossover."
    },
    {
        "name": "Bollinger Bands Mean Reversion",
        "class_path": "argo.strategies.mean_reversion.BBMeanReversionStrategy",
        "description": "Mean-reversion strategy that buys below lower band and closes at upper band / mean."
    },
    {
        "name": "RSI Mean Reversion",
        "class_path": "argo.strategies.rsi.RSIStrategy",
        "description": "Oscillator strategy buying when oversold (<30) and exiting when overbought (>70)."
    },
    {
        "name": "MACD Momentum Strategy",
        "class_path": "argo.strategies.macd.MACDStrategy",
        "description": "Momentum strategy trading MACD line crossovers with the signal line."
    },
    {
        "name": "Donchian Breakout (Turtle)",
        "class_path": "argo.strategies.donchian_breakout.DonchianBreakoutStrategy",
        "description": "Classic Turtle Trading breakout system on N-period channel highs and lows."
    },
    {
        "name": "SuperTrend Volatility Breakout",
        "class_path": "argo.strategies.supertrend_breakout.SuperTrendBreakoutStrategy",
        "description": "SuperTrend ATR volatility breakout trend-following system with dynamic trailing stops and multi-factor filtering."
    },
    {
        "name": "Kaufman Adaptive Trend Strategy",
        "class_path": "argo.strategies.kama_trend.KaufmanAdaptiveTrendStrategy",
        "description": "Adaptive trend-following using Kaufman Efficiency Ratio (KAMA) to filter noise and capture trends."
    },
    {
        "name": "Triple EMA Continuation Strategy",
        "class_path": "argo.strategies.triple_ma_trend.TripleMAContinuationStrategy",
        "description": "Multi-horizon structural trend alignment with pullback continuation triggers and risk forecasting."
    },
    {
        "name": "Dual Momentum Strategy",
        "class_path": "argo.strategies.dual_momentum.DualMomentumStrategy",
        "description": "Dual momentum system combining macro 200-SMA regime gating with momentum breakout execution and multi-factor risk controls."
    },
    {
        "name": "Buy and Hold Benchmark",
        "class_path": "argo.strategies.buy_and_hold.BuyAndHoldStrategy",
        "description": "Baseline passive benchmark holding an asset from start to evaluate strategy alpha."
    },
]


def discover_strategies():
    """Returns available strategy choices for Strategy.class_path field."""
    return [(s["class_path"], s["name"]) for s in DEFAULT_STRATEGIES]


def load_strategies_from_package(package_name: str = "argo.strategies"):
    """
    Dynamically discovers all NautilusStrategy subclasses in the package
    and creates/updates corresponding Strategy database records.
    """
    Strategy = apps.get_model("argo", "Strategy")
    package = importlib.import_module(package_name)
    loaded = []

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        full_module_name = f"{package_name}.{module_name}"
        try:
            module = importlib.import_module(full_module_name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, NautilusStrategy)
                    and attr is not NautilusStrategy
                    and attr.__module__ == full_module_name
                ):
                    class_path = f"{full_module_name}.{attr.__name__}"
                    doc = inspect.getdoc(attr) or ""
                    name = attr.__name__.replace("Strategy", " Strategy").strip()
                    obj, _ = Strategy.objects.update_or_create(
                        class_path=class_path,
                        defaults={"name": name, "description": doc.strip()}
                    )
                    loaded.append(obj)
        except Exception as e:
            print(f"[ERROR] Failed loading strategies from {full_module_name}: {e}")

    return loaded


def populate_default_strategies():
    """Populates the database Strategy model with default benchmark strategies."""
    return load_strategies_from_package("argo.strategies")


def load_strategies_from_db(node: TradingNode):
    """
    Finds the active portfolio in the database and loads its strategy instances
    into the trading node.
    """
    Portfolio = apps.get_model("argo", "Portfolio")
    try:
        active_portfolio = Portfolio.objects.get(is_active=True)
    except (Portfolio.DoesNotExist, Portfolio.MultipleObjectsReturned):
        return

    instances = (
        active_portfolio.strategy_instances.filter(is_active=True)
        if hasattr(active_portfolio, "strategy_instances")
        else apps.get_model("argo", "StrategyInstance").objects.filter(is_active=True)
    )

    for instance in instances:
        try:
            module_path, class_name = instance.strategy_model.class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            strategy_class = getattr(module, class_name)
            bar_type = BarType.from_str(instance.params.get("bar_type", "1-MINUTE-BAR-ASK-BID-LAST"))

            config_class = getattr(module, f"{class_name}Config", None)
            if config_class:
                config = config_class(
                    instrument_id=instance.instrument_id,
                    bar_type=str(bar_type),
                    **{k: v for k, v in instance.params.items() if k not in ["bar_type", "instrument_id"]}
                )
                strategy = strategy_class(config=config)
            else:
                strategy = strategy_class(instrument_id=instance.instrument_id, bar_type=bar_type, **instance.params)

            node.add_strategy(strategy)
        except Exception as e:
            print(f"[ERROR] Failed to load strategy instance {instance.id}: {e}")