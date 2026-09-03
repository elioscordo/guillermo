import datetime
import itertools
import random
from typing import Dict, Any, List, Optional

from argo.backtest.results import BacktestResult, OptimizationReport
from argo.backtest.runner import StrategyBacktestRunner


class ParameterGrid:
    """Represents a discrete parameter search space."""

    def __init__(self, param_ranges: Dict[str, List[Any]]):
        self.param_ranges = param_ranges

    def generate_combinations(self, max_samples: Optional[int] = None) -> List[Dict[str, Any]]:
        """Generates cartesian product or random samples from the grid."""
        keys = list(self.param_ranges.keys())
        values = list(self.param_ranges.values())
        all_combos = [dict(zip(keys, prod)) for prod in itertools.product(*values)]

        if max_samples and max_samples < len(all_combos):
            return random.sample(all_combos, max_samples)
        return all_combos


class ParameterOptimizer:
    """
    Grid and sampling parameter optimizer for trading strategy instances.
    Evaluates candidate parameters against objective functions (Sharpe, Calmar, EV, Profit Factor).
    """

    def __init__(self, runner: Optional[StrategyBacktestRunner] = None, objective: str = "sharpe"):
        self.runner = runner or StrategyBacktestRunner()
        self.objective = objective

    def optimize(
        self,
        instance,
        param_grid: ParameterGrid,
        start: datetime.datetime,
        end: datetime.datetime,
        max_evaluations: Optional[int] = 50,
        apply_best: bool = False,
    ) -> OptimizationReport:
        """Runs optimization sweeps across parameter combinations."""
        combinations = param_grid.generate_combinations(max_samples=max_evaluations)
        leaderboard: List[Dict[str, Any]] = []
        best_result: Optional[BacktestResult] = None
        best_score = -float("inf")
        best_params: Dict[str, Any] = {}

        for combo in combinations:
            res = self.runner.run(instance, start, end, params_override=combo)
            score = self._calculate_score(res)
            entry = {
                "params": combo,
                "score": round(score, 4),
                "total_pnl": round(res.total_pnl, 2),
                "return_pct": round(res.return_pct, 4),
                "sharpe_ratio": res.sharpe_ratio,
                "max_drawdown_pct": res.max_drawdown_pct,
                "win_rate": res.win_rate,
                "total_trades": res.total_trades,
            }
            leaderboard.append(entry)

            if score > best_score:
                best_score = score
                best_score = score
                best_params = combo
                best_result = res

        leaderboard.sort(key=lambda x: x["score"], reverse=True)

        if apply_best and best_params:
            merged = {**(instance.params or {}), **best_params}
            instance.params = merged
            instance.save(update_fields=["params"])

        return OptimizationReport(
            instance_id=instance.id,
            objective=self.objective,
            total_iterations=len(combinations),
            best_params=best_params,
            best_result=best_result,
            leaderboard=leaderboard,
        )

    def _calculate_score(self, res: BacktestResult) -> float:
        if self.objective == "calmar":
            return res.calmar_ratio
        if self.objective == "profit_factor":
            return res.profit_factor
        if self.objective == "pnl":
            return res.total_pnl
        return res.sharpe_ratio  # Default to Sharpe ratio

    def get_default_grid(self, strategy_model) -> Dict[str, List[Any]]:
        """Provides default parameter grid based on strategy type."""
        class_name = strategy_model.class_path.split(".")[-1] if strategy_model else ""
        if "SuperTrend" in class_name:
            return {
                "atr_period": [10, 14, 20],
                "atr_multiplier": [2.5, 3.0, 3.5],
                "min_adx": [20.0, 25.0, 30.0],
            }
        elif "Kaufman" in class_name or "KAMA" in class_name:
            return {
                "er_period": [8, 10, 14],
                "min_efficiency": [0.25, 0.30, 0.40],
                "slow_period": [20, 30, 40],
            }
        elif "TripleMA" in class_name:
            return {
                "fast_period": [8, 10, 12],
                "medium_period": [25, 30, 40],
                "slow_period": [80, 100, 150],
            }
        return {
            "trade_size": [50.0, 100.0, 200.0],
        }
