"""
Data Analyzer

Analyzes historical trade data and identifies patterns.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
import logging
import math
import statistics

import pandas as pd
import numpy as np

from ..core.config import get_config
from ..core.logging import get_logger
from ..core.database import get_database
from ..models.trades import Trade, TradeStatus
from ..models.trade_cycles import TradeCycle, CycleStatus


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of a data analysis."""
    analysis_id: str
    analysis_type: str
    timestamp: datetime
    metrics: Dict[str, float] = field(default_factory=dict)
    insights: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None


@dataclass
class StrategyComparison:
    """Comparison of strategy performance."""
    strategy_a_id: str
    strategy_b_id: str
    metric: str
    value_a: float
    value_b: float
    difference: float
    significance: float
    winner: Optional[str] = None


class DataAnalyzer:
    """
    Analyzes historical trade data and provides insights.
    
    Capabilities:
    - Strategy performance analysis
    - Trade pattern detection
    - Statistical analysis
    - Strategy comparison
    """
    
    def __init__(self):
        """Initialize the data analyzer."""
        self.logger = get_logger("ai_research.analyzer")
        self.db = get_database()
    
    def analyze_strategy_performance(
        self,
        strategy_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_trades: int = 10
    ) -> AnalysisResult:
        """
        Analyze the performance of a specific strategy.
        
        Args:
            strategy_id: Strategy identifier
            start_date: Optional start date
            end_date: Optional end date
            min_trades: Minimum number of trades for meaningful analysis
            
        Returns:
            AnalysisResult with performance metrics
        """
        result = AnalysisResult(
            analysis_id=f"perf_{strategy_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            analysis_type="strategy_performance",
            timestamp=datetime.utcnow()
        )
        
        try:
            # Get trade cycles for this strategy
            cycles = self._get_strategy_cycles(strategy_id, start_date, end_date)
            
            if len(cycles) < min_trades:
                result.warnings.append(f"Insufficient data: {len(cycles)} trades < {min_trades} minimum")
                return result
            
            # Calculate metrics
            metrics = self._calculate_performance_metrics(cycles)
            result.metrics = metrics
            
            # Generate insights
            insights = self._generate_performance_insights(metrics, cycles)
            result.insights = insights
            
            # Store raw data
            result.data = {
                "strategy_id": strategy_id,
                "num_cycles": len(cycles),
                "cycles": [self._cycle_to_dict(c) for c in cycles]
            }
            
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"Error analyzing strategy performance: {e}")
        
        return result
    
    def compare_strategies(
        self,
        strategy_ids: List[str],
        metric: str = "net_pnl",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[StrategyComparison]:
        """
        Compare multiple strategies.
        
        Args:
            strategy_ids: List of strategy identifiers
            metric: Metric to compare
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            List of StrategyComparison objects
        """
        comparisons = []
        
        # Get performance for each strategy
        performances = {}
        for strategy_id in strategy_ids:
            result = self.analyze_strategy_performance(
                strategy_id, start_date, end_date
            )
            if result.metrics:
                performances[strategy_id] = result.metrics
        
        # Compare each pair
        for i, strategy_a in enumerate(strategy_ids):
            for strategy_b in strategy_ids[i+1:]:
                if strategy_a in performances and strategy_b in performances:
                    comparison = self._compare_pair(
                        strategy_a, strategy_b, metric, performances
                    )
                    comparisons.append(comparison)
        
        return comparisons
    
    def analyze_trade_patterns(
        self,
        strategy_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> AnalysisResult:
        """
        Analyze trade patterns.
        
        Args:
            strategy_id: Optional strategy filter
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            AnalysisResult with pattern analysis
        """
        result = AnalysisResult(
            analysis_id=f"pattern_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            analysis_type="trade_patterns",
            timestamp=datetime.utcnow()
        )
        
        try:
            # Get cycles
            cycles = self._get_strategy_cycles(strategy_id, start_date, end_date)
            
            if len(cycles) < 10:
                result.warnings.append(f"Insufficient data: {len(cycles)} trades")
                return result
            
            # Analyze patterns
            patterns = self._detect_patterns(cycles)
            result.metrics = patterns
            result.insights = self._generate_pattern_insights(patterns)
            
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"Error analyzing trade patterns: {e}")
        
        return result
    
    def analyze_execution_quality(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> AnalysisResult:
        """
        Analyze execution quality.
        
        Args:
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            AnalysisResult with execution quality metrics
        """
        result = AnalysisResult(
            analysis_id=f"exec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            analysis_type="execution_quality",
            timestamp=datetime.utcnow()
        )
        
        try:
            # Get trades
            trades = self._get_trades(start_date, end_date)
            
            if len(trades) < 10:
                result.warnings.append(f"Insufficient data: {len(trades)} trades")
                return result
            
            # Calculate execution metrics
            metrics = self._calculate_execution_metrics(trades)
            result.metrics = metrics
            result.insights = self._generate_execution_insights(metrics)
            
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"Error analyzing execution quality: {e}")
        
        return result
    
    def _get_strategy_cycles(
        self,
        strategy_id: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> List[TradeCycle]:
        """
        Get trade cycles for a strategy.
        
        Args:
            strategy_id: Optional strategy filter
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            List of TradeCycle objects
        """
        try:
            with self.db.get_session() as session:
                query = session.query(TradeCycle)
                
                if strategy_id:
                    query = query.filter(TradeCycle.strategy_id == strategy_id)
                
                if start_date:
                    query = query.filter(TradeCycle.opened_time >= start_date)
                
                if end_date:
                    query = query.filter(TradeCycle.closed_time <= end_date)
                
                cycles = query.all()
                return cycles
        except Exception as e:
            self.logger.error(f"Error getting strategy cycles: {e}")
            return []
    
    def _get_trades(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> List[Trade]:
        """
        Get trades from database.
        
        Args:
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            List of Trade objects
        """
        try:
            with self.db.get_session() as session:
                query = session.query(Trade)
                
                if start_date:
                    query = query.filter(Trade.open_time >= start_date)
                
                if end_date:
                    query = query.filter(Trade.close_time <= end_date)
                
                trades = query.all()
                return trades
        except Exception as e:
            self.logger.error(f"Error getting trades: {e}")
            return []
    
    def _calculate_performance_metrics(self, cycles: List[TradeCycle]) -> Dict[str, float]:
        """
        Calculate performance metrics from trade cycles.
        
        Args:
            cycles: List of TradeCycle objects
            
        Returns:
            Dictionary of metrics
        """
        metrics = {}
        
        if not cycles:
            return metrics
        
        # Basic metrics
        total_cycles = len(cycles)
        completed_cycles = [c for c in cycles if c.status == CycleStatus.CLOSED.value]
        
        if not completed_cycles:
            return metrics
        
        # P&L metrics
        pnls = [c.combined_pnl for c in completed_cycles]
        net_pnl = sum(pnls)
        avg_pnl = net_pnl / len(completed_cycles)
        
        # Win/loss metrics
        winning_cycles = [c for c in completed_cycles if c.combined_pnl > 0]
        losing_cycles = [c for c in completed_cycles if c.combined_pnl < 0]
        win_rate = len(winning_cycles) / len(completed_cycles) if completed_cycles else 0
        
        # Profit factor
        total_wins = sum(c.combined_pnl for c in winning_cycles)
        total_losses = sum(abs(c.combined_pnl) for c in losing_cycles)
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Drawdown
        running_pnl = []
        current_pnl = 0
        for pnl in pnls:
            current_pnl += pnl
            running_pnl.append(current_pnl)
        
        max_pnl = max(running_pnl) if running_pnl else 0
        min_pnl = min(running_pnl) if running_pnl else 0
        max_drawdown = max_pnl - min_pnl if max_pnl > 0 else 0
        max_drawdown_percent = (max_drawdown / max_pnl * 100) if max_pnl > 0 else 0
        
        # Holding time
        holding_times = []
        for c in completed_cycles:
            if c.opened_time and c.closed_time:
                holding_times.append((c.closed_time - c.opened_time).total_seconds() / 60)
        
        avg_holding_time = sum(holding_times) / len(holding_times) if holding_times else 0
        
        # Costs
        total_commission = sum(c.total_commission for c in completed_cycles)
        total_swap = sum(c.total_swap for c in completed_cycles)
        total_slippage = sum(c.total_slippage for c in completed_cycles)
        total_costs = total_commission + total_swap + total_slippage
        
        # Net P&L with costs
        net_pnl_with_costs = net_pnl - total_costs
        
        # Sharpe ratio (simplified)
        if len(pnls) > 1:
            std_pnl = statistics.stdev(pnls)
            sharpe_ratio = avg_pnl / std_pnl if std_pnl > 0 else 0
        else:
            sharpe_ratio = 0
        
        metrics = {
            "total_cycles": total_cycles,
            "completed_cycles": len(completed_cycles),
            "net_pnl": net_pnl,
            "avg_pnl": avg_pnl,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "max_drawdown_percent": max_drawdown_percent,
            "avg_holding_time_minutes": avg_holding_time,
            "total_commission": total_commission,
            "total_swap": total_swap,
            "total_slippage": total_slippage,
            "total_costs": total_costs,
            "net_pnl_with_costs": net_pnl_with_costs,
            "sharpe_ratio": sharpe_ratio,
            "winning_cycles": len(winning_cycles),
            "losing_cycles": len(losing_cycles),
        }
        
        return metrics
    
    def _generate_performance_insights(
        self,
        metrics: Dict[str, float],
        cycles: List[TradeCycle]
    ) -> List[str]:
        """
        Generate insights from performance metrics.
        
        Args:
            metrics: Performance metrics
            cycles: List of TradeCycle objects
            
        Returns:
            List of insight strings
        """
        insights = []
        
        # Win rate
        win_rate = metrics.get("win_rate", 0)
        if win_rate > 0.6:
            insights.append(f"High win rate: {win_rate:.1%}")
        elif win_rate < 0.4:
            insights.append(f"Low win rate: {win_rate:.1%}")
        
        # Profit factor
        profit_factor = metrics.get("profit_factor", 0)
        if profit_factor > 2:
            insights.append(f"Excellent profit factor: {profit_factor:.2f}")
        elif profit_factor > 1.5:
            insights.append(f"Good profit factor: {profit_factor:.2f}")
        elif profit_factor < 1:
            insights.append(f"Poor profit factor: {profit_factor:.2f}")
        
        # Drawdown
        max_drawdown_percent = metrics.get("max_drawdown_percent", 0)
        if max_drawdown_percent > 20:
            insights.append(f"High drawdown: {max_drawdown_percent:.1f}%")
        elif max_drawdown_percent < 5:
            insights.append(f"Low drawdown: {max_drawdown_percent:.1f}%")
        
        # Sharpe ratio
        sharpe_ratio = metrics.get("sharpe_ratio", 0)
        if sharpe_ratio > 2:
            insights.append(f"Excellent Sharpe ratio: {sharpe_ratio:.2f}")
        elif sharpe_ratio > 1:
            insights.append(f"Good Sharpe ratio: {sharpe_ratio:.2f}")
        
        # Costs
        total_costs = metrics.get("total_costs", 0)
        net_pnl = metrics.get("net_pnl", 0)
        if total_costs > abs(net_pnl) * 0.5:
            insights.append(f"High costs relative to P&L: {total_costs:.2f}")
        
        return insights
    
    def _detect_patterns(self, cycles: List[TradeCycle]) -> Dict[str, float]:
        """
        Detect trade patterns.
        
        Args:
            cycles: List of TradeCycle objects
            
        Returns:
            Dictionary of pattern metrics
        """
        patterns = {}
        
        if not cycles:
            return patterns
        
        # Time-based patterns
        hourly_distribution = self._calculate_hourly_distribution(cycles)
        patterns["hourly_distribution"] = hourly_distribution
        
        # Day of week patterns
        day_of_week_distribution = self._calculate_day_of_week_distribution(cycles)
        patterns["day_of_week_distribution"] = day_of_week_distribution
        
        # Holding time patterns
        holding_time_stats = self._calculate_holding_time_stats(cycles)
        patterns["holding_time_stats"] = holding_time_stats
        
        # P&L patterns
        pnl_stats = self._calculate_pnl_stats(cycles)
        patterns["pnl_stats"] = pnl_stats
        
        return patterns
    
    def _generate_pattern_insights(self, patterns: Dict[str, float]) -> List[str]:
        """
        Generate insights from detected patterns.
        
        Args:
            patterns: Detected patterns
            
        Returns:
            List of insight strings
        """
        insights = []
        
        # Hourly distribution
        hourly = patterns.get("hourly_distribution", {})
        if hourly:
            best_hour = max(hourly, key=hourly.get)
            worst_hour = min(hourly, key=hourly.get)
            insights.append(f"Best hour: {best_hour} ({hourly[best_hour]:.1%} of trades)")
            insights.append(f"Worst hour: {worst_hour} ({hourly[worst_hour]:.1%} of trades)")
        
        # Day of week distribution
        day_of_week = patterns.get("day_of_week_distribution", {})
        if day_of_week:
            best_day = max(day_of_week, key=day_of_week.get)
            worst_day = min(day_of_week, key=day_of_week.get)
            insights.append(f"Best day: {best_day} ({day_of_week[best_day]:.1%} of trades)")
        
        # Holding time
        holding_stats = patterns.get("holding_time_stats", {})
        avg_holding = holding_stats.get("average", 0)
        if avg_holding > 60:
            insights.append(f"Average holding time: {avg_holding:.0f} minutes")
        
        return insights
    
    def _calculate_execution_metrics(self, trades: List[Trade]) -> Dict[str, float]:
        """
        Calculate execution quality metrics.
        
        Args:
            trades: List of Trade objects
            
        Returns:
            Dictionary of execution metrics
        """
        metrics = {}
        
        if not trades:
            return metrics
        
        # Slippage metrics
        slippages = [t.slippage for t in trades if t.slippage is not None]
        if slippages:
            metrics["avg_slippage"] = sum(slippages) / len(slippages)
            metrics["max_slippage"] = max(slippages)
            metrics["min_slippage"] = min(slippages)
        
        # Execution delay (would need timestamp data)
        # For now, skip
        
        # Commission
        commissions = [t.commission for t in trades if t.commission is not None]
        if commissions:
            metrics["avg_commission"] = sum(commissions) / len(commissions)
            metrics["total_commission"] = sum(commissions)
        
        # Swap
        swaps = [t.swap for t in trades if t.swap is not None]
        if swaps:
            metrics["avg_swap"] = sum(swaps) / len(swaps)
            metrics["total_swap"] = sum(swaps)
        
        return metrics
    
    def _generate_execution_insights(self, metrics: Dict[str, float]) -> List[str]:
        """
        Generate insights from execution metrics.
        
        Args:
            metrics: Execution metrics
            
        Returns:
            List of insight strings
        """
        insights = []
        
        # Slippage
        avg_slippage = metrics.get("avg_slippage", 0)
        if avg_slippage > 1:
            insights.append(f"High average slippage: {avg_slippage:.2f} points")
        elif avg_slippage < 0.5:
            insights.append(f"Low average slippage: {avg_slippage:.2f} points")
        
        # Commission
        total_commission = metrics.get("total_commission", 0)
        if total_commission > 10:
            insights.append(f"High commission costs: {total_commission:.2f}")
        
        return insights
    
    def _compare_pair(
        self,
        strategy_a: str,
        strategy_b: str,
        metric: str,
        performances: Dict[str, Dict[str, float]]
    ) -> StrategyComparison:
        """
        Compare two strategies on a specific metric.
        
        Args:
            strategy_a: First strategy ID
            strategy_b: Second strategy ID
            metric: Metric to compare
            performances: Performance metrics for both strategies
            
        Returns:
            StrategyComparison object
        """
        value_a = performances.get(strategy_a, {}).get(metric, 0)
        value_b = performances.get(strategy_b, {}).get(metric, 0)
        difference = value_a - value_b
        
        # Determine winner
        winner = None
        if metric in ["net_pnl", "win_rate", "profit_factor", "sharpe_ratio"]:
            # Higher is better
            if value_a > value_b:
                winner = strategy_a
            elif value_b > value_a:
                winner = strategy_b
        else:
            # Lower is better (e.g., drawdown, costs)
            if value_a < value_b:
                winner = strategy_a
            elif value_b < value_a:
                winner = strategy_b
        
        return StrategyComparison(
            strategy_a_id=strategy_a,
            strategy_b_id=strategy_b,
            metric=metric,
            value_a=value_a,
            value_b=value_b,
            difference=difference,
            significance=abs(difference) / max(abs(value_a), abs(value_b), 1),
            winner=winner
        )
    
    def _cycle_to_dict(self, cycle: TradeCycle) -> Dict[str, Any]:
        """
        Convert TradeCycle to dictionary.
        
        Args:
            cycle: TradeCycle object
            
        Returns:
            Dictionary representation
        """
        return {
            "cycle_id": cycle.cycle_id,
            "strategy_id": cycle.strategy_id,
            "instrument": cycle.instrument,
            "lot_size": cycle.lot_size,
            "direction": cycle.direction,
            "status": cycle.status,
            "combined_pnl": cycle.combined_pnl,
            "opened_time": cycle.opened_time.isoformat() if cycle.opened_time else None,
            "closed_time": cycle.closed_time.isoformat() if cycle.closed_time else None,
        }
    
    def _calculate_hourly_distribution(self, cycles: List[TradeCycle]) -> Dict[int, float]:
        """
        Calculate hourly distribution of trades.
        
        Args:
            cycles: List of TradeCycle objects
            
        Returns:
            Dictionary of hour -> percentage
        """
        hourly = {}
        total = len(cycles)
        
        for cycle in cycles:
            if cycle.opened_time:
                hour = cycle.opened_time.hour
                hourly[hour] = hourly.get(hour, 0) + 1
        
        # Convert to percentages
        return {h: (count / total * 100) for h, count in hourly.items()}
    
    def _calculate_day_of_week_distribution(self, cycles: List[TradeCycle]) -> Dict[int, float]:
        """
        Calculate day of week distribution of trades.
        
        Args:
            cycles: List of TradeCycle objects
            
        Returns:
            Dictionary of day (0-6) -> percentage
        """
        daily = {}
        total = len(cycles)
        
        for cycle in cycles:
            if cycle.opened_time:
                day = cycle.opened_time.weekday()
                daily[day] = daily.get(day, 0) + 1
        
        # Convert to percentages
        return {d: (count / total * 100) for d, count in daily.items()}
    
    def _calculate_holding_time_stats(self, cycles: List[TradeCycle]) -> Dict[str, float]:
        """
        Calculate holding time statistics.
        
        Args:
            cycles: List of TradeCycle objects
            
        Returns:
            Dictionary of holding time statistics
        """
        holding_times = []
        
        for cycle in cycles:
            if cycle.opened_time and cycle.closed_time:
                holding_minutes = (cycle.closed_time - cycle.opened_time).total_seconds() / 60
                holding_times.append(holding_minutes)
        
        if not holding_times:
            return {}
        
        return {
            "average": sum(holding_times) / len(holding_times),
            "min": min(holding_times),
            "max": max(holding_times),
            "median": statistics.median(holding_times),
            "std_dev": statistics.stdev(holding_times) if len(holding_times) > 1 else 0
        }
    
    def _calculate_pnl_stats(self, cycles: List[TradeCycle]) -> Dict[str, float]:
        """
        Calculate P&L statistics.
        
        Args:
            cycles: List of TradeCycle objects
            
        Returns:
            Dictionary of P&L statistics
        """
        pnls = [c.combined_pnl for c in cycles if c.combined_pnl is not None]
        
        if not pnls:
            return {}
        
        return {
            "average": sum(pnls) / len(pnls),
            "min": min(pnls),
            "max": max(pnls),
            "median": statistics.median(pnls),
            "std_dev": statistics.stdev(pnls) if len(pnls) > 1 else 0
        }


# Global data analyzer instance
_data_analyzer: Optional[DataAnalyzer] = None


def get_data_analyzer() -> DataAnalyzer:
    """
    Get the global data analyzer instance.
    
    Returns:
        DataAnalyzer instance
    """
    global _data_analyzer
    if _data_analyzer is None:
        _data_analyzer = DataAnalyzer()
    return _data_analyzer
