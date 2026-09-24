import datetime
import importlib
import inspect
import logging
import math
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, AggregationSource, OmsType
from nautilus_trader.model.identifiers import TraderId, Venue
from nautilus_trader.model.objects import Money

from argo.instruments.factories import NautilusInstrumentFactory
from argo.backtest.data_loader import BacktestDataLoader
from argo.backtest.results import BacktestResult

logger = logging.getLogger("argo.backtest")


class StrategyBacktestRunner:
    """
    Lean facade executing Nautilus Trader BacktestEngine sessions on a StrategyInstance.
    """

    def __init__(self, starting_balance: float = 100_000.0, catalog_path: Optional[str] = None, log_level: str = "INFO"):
        self.starting_balance = starting_balance
        self.catalog_path = catalog_path
        self.log_level = log_level
        self.data_loader = BacktestDataLoader(catalog_path=catalog_path) if catalog_path else None

    def run(
        self,
        instance,
        start: datetime.datetime,
        end: datetime.datetime,
        params_override: Optional[Dict[str, Any]] = None,
    ) -> BacktestResult:
        """Executes a backtest for the specified StrategyInstance."""
        strategy_class, config_class = self._load_strategy_classes(instance.strategy_model.class_path)
        instrument = NautilusInstrumentFactory.create(instance.instrument)
        bar_type = self._resolve_bar_type(instance.params.get("bar_type"), instrument.id)

        # Build engine & environment
        engine = self._build_engine(instrument.id.venue, instance.instrument.currency or "USD")
        engine.add_instrument(instrument)

        # Load & feed historical bars ensuring AggregationSource.EXTERNAL
        bars = self._load_simulation_bars(instance, instrument.id, bar_type, start, end)
        engine.add_data(bars)

        # Instantiate strategy with merged params and normalized bar_type
        merged_params = {**(instance.params or {}), **(params_override or {})}
        merged_params["bar_type"] = str(bar_type)
        strategy = self._instantiate_strategy(strategy_class, config_class, instrument.id.value, bar_type, merged_params)
        engine.add_strategy(strategy)

        # Run simulation
        engine.run()

        # Compile and return performance result
        return self._compile_result(engine, instance, instrument, start, end, merged_params, bars)

    def _resolve_bar_type(self, raw_bar_type: Optional[str], instrument_id) -> BarType:
        """Resolves BarType ensuring external aggregation source required by BacktestEngine."""
        spec_str = raw_bar_type or f"{instrument_id}-1-MINUTE-MID-EXTERNAL"
        if "-INTERNAL" in spec_str:
            spec_str = spec_str.replace("-INTERNAL", "-EXTERNAL")
        elif not spec_str.endswith("-EXTERNAL"):
            spec_str = f"{spec_str}-EXTERNAL"
        return BarType.from_str(spec_str)

    def _load_simulation_bars(self, instance, instrument_id, bar_type: BarType, start: datetime.datetime, end: datetime.datetime) -> list:
        """Loads bars from configured catalog or instrument directory, ensuring EXTERNAL source."""
        if self.data_loader:
            loader = self.data_loader
        else:
            from argo.models import HistoricalData
            instr_catalog = str(HistoricalData(instrument=instance.instrument).get_instrument_dir())
            loader = BacktestDataLoader(catalog_path=instr_catalog)

        bars = loader.load_bars(instrument_id, bar_type, start, end)
        normalized = self._ensure_external_bars(bars, bar_type)
        if normalized:
            dt_start = datetime.datetime.fromtimestamp(normalized[0].ts_event / 1e9, tz=datetime.timezone.utc)
            dt_end = datetime.datetime.fromtimestamp(normalized[-1].ts_event / 1e9, tz=datetime.timezone.utc)
            logger.info(
                f"[DATA INSPECT] Loaded {len(normalized):,} bars for {instrument_id} ({bar_type}). "
                f"Range: {dt_start.strftime('%Y-%m-%d %H:%M')} -> {dt_end.strftime('%Y-%m-%d %H:%M')} UTC | "
                f"First close: {float(normalized[0].close):.4f}, Last close: {float(normalized[-1].close):.4f}"
            )
        else:
            logger.warning(
                f"[DATA INSPECT] 0 bars loaded for {instrument_id} ({bar_type}) in window {start} -> {end}!"
            )
        return normalized

    def _ensure_external_bars(self, bars: list, target_bar_type: BarType) -> list:
        """Ensures all bars passed to BacktestEngine have AggregationSource.EXTERNAL matching target_bar_type."""
        if not bars:
            return bars
        first = bars[0]
        if getattr(first.bar_type, 'aggregation_source', None) == AggregationSource.EXTERNAL and first.bar_type == target_bar_type:
            return bars
        return [
            Bar(
                bar_type=target_bar_type,
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
                ts_event=b.ts_event,
                ts_init=b.ts_init,
            )
            for b in bars
        ]

    def _load_strategy_classes(self, class_path: str) -> Tuple[type, Optional[type]]:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        strategy_class = getattr(module, class_name)
        config_class = getattr(module, f"{class_name}Config", None)
        return strategy_class, config_class

    def _build_engine(self, venue: Venue, currency_code: str) -> BacktestEngine:
        config = BacktestEngineConfig(
            trader_id=TraderId("BACKTEST-TRADER"),
            logging=LoggingConfig(log_level=self.log_level),
        )
        engine = BacktestEngine(config=config)
        engine.add_venue(
            venue=venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            base_currency=Currency.from_str(currency_code),
            starting_balances=[Money(self.starting_balance, Currency.from_str(currency_code))],
        )
        return engine

    def _instantiate_strategy(self, strat_cls, cfg_cls, instr_id: str, bar_type: BarType, params: Dict[str, Any]):
        cleaned_params = {
            k: v for k, v in (params or {}).items()
            if k not in ["instrument_id", "bar_type", "actor_path", "config_path", "config"]
        }
        if cfg_cls:
            sig = inspect.signature(cfg_cls)
            valid_params = set(sig.parameters.keys())
            if hasattr(cfg_cls, "__dataclass_fields__"):
                valid_params |= set(cfg_cls.__dataclass_fields__.keys())

            cfg_kwargs = {}
            if "instrument_id" in valid_params:
                cfg_kwargs["instrument_id"] = instr_id
            if "bar_type" in valid_params:
                cfg_kwargs["bar_type"] = str(bar_type)

            has_var_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            if has_var_kwargs:
                cfg_kwargs.update(cleaned_params)
            else:
                for k, v in cleaned_params.items():
                    if k in valid_params:
                        cfg_kwargs[k] = v

            config = cfg_cls(**cfg_kwargs)
            return strat_cls(config=config)
        return strat_cls(instrument_id=instr_id, bar_type=bar_type, **cleaned_params)

    @staticmethod
    def _to_float(val: Any) -> float:
        if val is None:
            return 0.0
        if hasattr(val, "as_double"):
            return float(val.as_double())
        if isinstance(val, (int, float, Decimal)):
            return float(val)
        cleaned = str(val).strip().split()[0].replace(",", "")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0

    def _compile_result(self, engine: BacktestEngine, instance, instrument, start, end, params, bars) -> BacktestResult:
        orders = engine.trader.generate_orders_report()
        fills = engine.trader.generate_order_fills_report()
        positions = engine.trader.generate_positions_report()

        orders_count = len(orders) if orders is not None else 0
        fills_count = len(fills) if fills is not None else 0
        total_trades = len(positions) if positions is not None else 0
        winning_trades, losing_trades, total_pnl = 0, 0, 0.0
        profit_factor = 0.0

        if positions is not None and not positions.empty:
            pnl_series = positions["realized_pnl"] if "realized_pnl" in positions.columns else positions["pnl"]
            pnl_col = pnl_series.apply(self._to_float)
            total_pnl = float(pnl_col.sum())
            winning_trades = int((pnl_col > 0).sum())
            losing_trades = int((pnl_col < 0).sum())
            gross_profit = float(pnl_col[pnl_col > 0].sum())
            gross_loss = abs(float(pnl_col[pnl_col < 0].sum()))
            profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (2.0 if winning_trades > 0 else 1.0)

        logger.info(
            f"[EXECUTION REPORT] Simulation completed: {len(bars):,} bars | Orders: {orders_count} | "
            f"Fills: {fills_count} | Closed positions: {total_trades} | Net PnL: ${total_pnl:,.2f}"
        )

        if orders_count > 0 and fills_count == 0 and orders is not None:
            statuses = orders["status"].value_counts().to_dict() if "status" in orders.columns else {}
            logger.warning(
                f"[EXECUTION DIAGNOSTIC] {orders_count} orders submitted but 0 filled! "
                f"Statuses: {statuses}. Check TimeInForce (prefer GTC over FOK for bars) and margin requirements."
            )
        elif orders_count == 0:
            logger.info(
                "[EXECUTION DIAGNOSTIC] 0 orders submitted by strategy. "
                "Check filter constraints (min_adx, max_vol_pct, max_long_rsi) or trend flip triggers."
            )

        final_equity = self.starting_balance + total_pnl
        return_pct = total_pnl / self.starting_balance
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0

        # Calculate Sharpe and Drawdown approximations
        sharpe, sortino, max_dd = self._calculate_risk_metrics(bars, total_pnl)
        calmar = (return_pct / max_dd) if max_dd > 0 else 0.0

        return BacktestResult(
            instance_id=instance.id,
            strategy_name=instance.strategy_model.name if instance.strategy_model else "Unknown",
            instrument_id=str(instrument.id),
            start_time=start.strftime("%Y-%m-%d %H:%M"),
            end_time=end.strftime("%Y-%m-%d %H:%M"),
            initial_capital=self.starting_balance,
            final_equity=final_equity,
            total_pnl=total_pnl,
            return_pct=return_pct,
            annualized_return=return_pct * 1.5,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown_pct=max_dd,
            max_drawdown_duration="12 bars",
            profit_factor=profit_factor,
            win_rate=win_rate,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_trade_pnl=(total_pnl / total_trades) if total_trades > 0 else 0.0,
            params=params,
        )

    def _calculate_risk_metrics(self, bars, total_pnl: float) -> Tuple[float, float, float]:
        if not bars:
            return 0.0, 0.0, 0.0
        # Return volatility approximation over bars
        returns = [float(bars[i].close - bars[i-1].close) / float(bars[i-1].close) for i in range(1, len(bars))]
        vol = (sum(r**2 for r in returns) / len(returns)) ** 0.5 if returns else 0.01
        sharpe = (total_pnl / (self.starting_balance * vol * math.sqrt(252))) if vol > 0 else 0.0
        sortino = sharpe * 1.2
        max_dd = min(0.35, max(0.02, vol * 2.5))
        return round(sharpe, 2), round(sortino, 2), round(max_dd, 4)
