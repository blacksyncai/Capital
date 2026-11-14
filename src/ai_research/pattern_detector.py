"""
Pattern Detector

Detects recurring patterns in trade data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
import logging
import statistics

import numpy as np

from .data_analyzer import DataAnalyzer, AnalysisResult


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Pattern:
    """Represents a detected pattern."""
    pattern_id: str
    pattern_type: str
    description: str
    frequency: float
    strength: float
    last_occurrence: datetime
    first_occurrence: datetime
    occurrences: int
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class PatternDetectionResult:
    """Result of pattern detection."""
    detection_id: str
    timestamp: datetime
    patterns: List[Pattern] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PatternDetector:
    """
    Detects recurring patterns in trade data.
    
    Pattern types:
    - Winning/losing streaks
    - Time-based patterns
    - Price-based patterns
    - Volume-based patterns
    - Strategy performance patterns
    """
    
    def __init__(self):
        """Initialize the pattern detector."""
        self.logger = logger
        self.data_analyzer = DataAnalyzer()
    
    def detect_all_patterns(
        self,
        strategy_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_occurrences: int = 3
    ) -> PatternDetectionResult:
        """
        Detect all pattern types.
        
        Args:
            strategy_id: Optional strategy filter
            start_date: Optional start date
            end_date: Optional end date
            min_occurrences: Minimum occurrences for a pattern
            
        Returns:
            PatternDetectionResult
        """
        result = PatternDetectionResult(
            detection_id=f"pattern_detect_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.utcnow()
        )
        
        try:
            # Get cycles
            cycles = self._get_cycles(strategy_id, start_date, end_date)
            
            if len(cycles) < min_occurrences:
                result.warnings.append(f"Insufficient data: {len(cycles)} cycles")
                return result
            
            # Detect different pattern types
            result.patterns.extend(self._detect_streak_patterns(cycles, min_occurrences))
            result.patterns.extend(self._detect_time_patterns(cycles, min_occurrences))
            result.patterns.extend(self._detect_pnl_patterns(cycles, min_occurrences))
            result.patterns.extend(self._detect_holding_time_patterns(cycles, min_occurrences))
            
            # Generate insights
            result.insights = self._generate_pattern_insights(result.patterns)
            
        except Exception as e:
            self.logger.error(f"Error detecting patterns: {e}")
        
        return result
    
    def detect_streak_patterns(
        self,
        strategy_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_streak_length: int = 3
    ) -> List[Pattern]:
        """
        Detect winning and losing streaks.
        
        Args:
            strategy_id: Optional strategy filter
            start_date: Optional start date
            end_date: Optional end date
            min_streak_length: Minimum streak length
            
        Returns:
            List of Pattern objects
        """
        cycles = self._get_cycles(strategy_id, start_date, end_date)
        return self._detect_streak_patterns(cycles, min_streak_length)
    
    def detect_time_patterns(
        self,
        strategy_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_occurrences: int = 3
    ) -> List[Pattern]:
        """
        Detect time-based patterns.
        
        Args:
            strategy_id: Optional strategy filter
            start_date: Optional start date
            end_date: Optional end date
            min_occurrences: Minimum occurrences
            
        Returns:
            List of Pattern objects
        """
        cycles = self._get_cycles(strategy_id, start_date, end_date)
        return self._detect_time_patterns(cycles, min_occurrences)
    
    def _get_cycles(
        self,
        strategy_id: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> List[Any]:
        """
        Get trade cycles from database.
        
        Args:
            strategy_id: Optional strategy filter
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            List of TradeCycle objects
        """
        # Import here to avoid circular imports
        from ..core.database import get_database
        from ..models.trade_cycles import TradeCycle
        
        try:
            db = get_database()
            with db.get_session() as session:
                query = session.query(TradeCycle)
                
                if strategy_id:
                    query = query.filter(TradeCycle.strategy_id == strategy_id)
                
                if start_date:
                    query = query.filter(TradeCycle.opened_time >= start_date)
                
                if end_date:
                    query = query.filter(TradeCycle.closed_time <= end_date)
                
                return query.all()
        except Exception as e:
            self.logger.error(f"Error getting cycles: {e}")
            return []
    
    def _detect_streak_patterns(self, cycles: List[Any], min_streak_length: int) -> List[Pattern]:
        """
        Detect winning and losing streaks.
        
        Args:
            cycles: List of TradeCycle objects
            min_streak_length: Minimum streak length
            
        Returns:
            List of Pattern objects
        """
        patterns = []
        
        if not cycles:
            return patterns
        
        # Sort by opened time
        sorted_cycles = sorted(cycles, key=lambda c: c.opened_time if c.opened_time else datetime.min)
        
        # Extract P&L
        pnls = [c.combined_pnl for c in sorted_cycles if c.combined_pnl is not None]
        
        if not pnls:
            return patterns
        
        # Find streaks
        current_streak = [pnls[0]]
        streaks = []
        
        for pnl in pnls[1:]:
            if (pnl > 0 and current_streak[-1] > 0) or (pnl < 0 and current_streak[-1] < 0):
                current_streak.append(pnl)
            else:
                if len(current_streak) >= min_streak_length:
                    streaks.append(current_streak.copy())
                current_streak = [pnl]
        
        # Don't forget the last streak
        if len(current_streak) >= min_streak_length:
            streaks.append(current_streak)
        
        # Create patterns from streaks
        winning_streaks = [s for s in streaks if all(p > 0 for p in s)]
        losing_streaks = [s for s in streaks if all(p < 0 for p in s)]
        
        # Winning streak pattern
        if winning_streaks:
            avg_length = sum(len(s) for s in winning_streaks) / len(winning_streaks)
            total_pnl = sum(sum(s) for s in winning_streaks)
            patterns.append(Pattern(
                pattern_id=f"winning_streak_{min_streak_length}",
                pattern_type="winning_streak",
                description=f"Winning streak of at least {min_streak_length} trades",
                frequency=len(winning_streaks) / len(streaks) if streaks else 0,
                strength=total_pnl / len(winning_streaks) if winning_streaks else 0,
                last_occurrence=sorted_cycles[-1].opened_time if sorted_cycles else datetime.utcnow(),
                first_occurrence=sorted_cycles[0].opened_time if sorted_cycles else datetime.utcnow(),
                occurrences=len(winning_streaks),
                metrics={
                    "average_length": avg_length,
                    "average_pnl_per_streak": total_pnl / len(winning_streaks) if winning_streaks else 0
                }
            ))
        
        # Losing streak pattern
        if losing_streaks:
            avg_length = sum(len(s) for s in losing_streaks) / len(losing_streaks)
            total_loss = sum(sum(s) for s in losing_streaks)
            patterns.append(Pattern(
                pattern_id=f"losing_streak_{min_streak_length}",
                pattern_type="losing_streak",
                description=f"Losing streak of at least {min_streak_length} trades",
                frequency=len(losing_streaks) / len(streaks) if streaks else 0,
                strength=abs(total_loss) / len(losing_streaks) if losing_streaks else 0,
                last_occurrence=sorted_cycles[-1].opened_time if sorted_cycles else datetime.utcnow(),
                first_occurrence=sorted_cycles[0].opened_time if sorted_cycles else datetime.utcnow(),
                occurrences=len(losing_streaks),
                metrics={
                    "average_length": avg_length,
                    "average_loss_per_streak": total_loss / len(losing_streaks) if losing_streaks else 0
                }
            ))
        
        return patterns
    
    def _detect_time_patterns(self, cycles: List[Any], min_occurrences: int) -> List[Pattern]:
        """
        Detect time-based patterns.
        
        Args:
            cycles: List of TradeCycle objects
            min_occurrences: Minimum occurrences
            
        Returns:
            List of Pattern objects
        """
        patterns = []
        
        if not cycles:
            return patterns
        
        # Hourly patterns
        hourly = {}
        for cycle in cycles:
            if cycle.opened_time:
                hour = cycle.opened_time.hour
                pnl = cycle.combined_pnl if cycle.combined_pnl is not None else 0
                if hour not in hourly:
                    hourly[hour] = {"count": 0, "total_pnl": 0, "winning": 0, "losing": 0}
                hourly[hour]["count"] += 1
                hourly[hour]["total_pnl"] += pnl
                if pnl > 0:
                    hourly[hour]["winning"] += 1
                else:
                    hourly[hour]["losing"] += 1
        
        # Find significant hours
        total_cycles = len(cycles)
        for hour, data in hourly.items():
            if data["count"] >= min_occurrences:
                win_rate = data["winning"] / data["count"] if data["count"] > 0 else 0
                avg_pnl = data["total_pnl"] / data["count"] if data["count"] > 0 else 0
                
                # Check if this hour is significantly different
                if win_rate > 0.6 or win_rate < 0.4 or abs(avg_pnl) > 1:
                    patterns.append(Pattern(
                        pattern_id=f"hour_{hour}",
                        pattern_type="time_hour",
                        description=f"Hour {hour}:00 - {hour}:59",
                        frequency=data["count"] / total_cycles,
                        strength=abs(avg_pnl),
                        last_occurrence=datetime.utcnow(),
                        first_occurrence=datetime.utcnow(),
                        occurrences=data["count"],
                        metrics={
                            "win_rate": win_rate,
                            "avg_pnl": avg_pnl,
                            "total_trades": data["count"]
                        }
                    ))
        
        # Day of week patterns
        day_of_week = {}
        for cycle in cycles:
            if cycle.opened_time:
                day = cycle.opened_time.weekday()
                pnl = cycle.combined_pnl if cycle.combined_pnl is not None else 0
                if day not in day_of_week:
                    day_of_week[day] = {"count": 0, "total_pnl": 0}
                day_of_week[day]["count"] += 1
                day_of_week[day]["total_pnl"] += pnl
        
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day, data in day_of_week.items():
            if data["count"] >= min_occurrences:
                avg_pnl = data["total_pnl"] / data["count"] if data["count"] > 0 else 0
                patterns.append(Pattern(
                    pattern_id=f"day_{day}",
                    pattern_type="time_day",
                    description=f"{day_names[day]}",
                    frequency=data["count"] / total_cycles,
                    strength=abs(avg_pnl),
                    last_occurrence=datetime.utcnow(),
                    first_occurrence=datetime.utcnow(),
                    occurrences=data["count"],
                    metrics={
                        "avg_pnl": avg_pnl,
                        "total_trades": data["count"]
                    }
                ))
        
        return patterns
    
    def _detect_pnl_patterns(self, cycles: List[Any], min_occurrences: int) -> List[Pattern]:
        """
        Detect P&L patterns.
        
        Args:
            cycles: List of TradeCycle objects
            min_occurrences: Minimum occurrences
            
        Returns:
            List of Pattern objects
        """
        patterns = []
        
        if not cycles:
            return patterns
        
        # P&L distribution
        pnls = [c.combined_pnl for c in cycles if c.combined_pnl is not None]
        
        if len(pnls) < min_occurrences:
            return patterns
        
        # Check for common P&L ranges
        # This is a simplified version
        positive_pnls = [p for p in pnls if p > 0]
        negative_pnls = [p for p in pnls if p < 0]
        
        if positive_pnls:
            avg_win = sum(positive_pnls) / len(positive_pnls)
            patterns.append(Pattern(
                pattern_id="positive_pnl",
                pattern_type="pnl_positive",
                description=f"Positive P&L pattern",
                frequency=len(positive_pnls) / len(pnls),
                strength=avg_win,
                last_occurrence=datetime.utcnow(),
                first_occurrence=datetime.utcnow(),
                occurrences=len(positive_pnls),
                metrics={
                    "avg_win": avg_win,
                    "max_win": max(positive_pnls),
                    "min_win": min(positive_pnls)
                }
            ))
        
        if negative_pnls:
            avg_loss = sum(negative_pnls) / len(negative_pnls)
            patterns.append(Pattern(
                pattern_id="negative_pnl",
                pattern_type="pnl_negative",
                description=f"Negative P&L pattern",
                frequency=len(negative_pnls) / len(pnls),
                strength=abs(avg_loss),
                last_occurrence=datetime.utcnow(),
                first_occurrence=datetime.utcnow(),
                occurrences=len(negative_pnls),
                metrics={
                    "avg_loss": avg_loss,
                    "max_loss": min(negative_pnls),
                    "min_loss": max(negative_pnls)
                }
            ))
        
        return patterns
    
    def _detect_holding_time_patterns(self, cycles: List[Any], min_occurrences: int) -> List[Pattern]:
        """
        Detect holding time patterns.
        
        Args:
            cycles: List of TradeCycle objects
            min_occurrences: Minimum occurrences
            
        Returns:
            List of Pattern objects
        """
        patterns = []
        
        if not cycles:
            return patterns
        
        # Holding time distribution
        holding_times = []
        for cycle in cycles:
            if cycle.opened_time and cycle.closed_time:
                holding_minutes = (cycle.closed_time - cycle.opened_time).total_seconds() / 60
                holding_times.append(holding_minutes)
        
        if len(holding_times) < min_occurrences:
            return patterns
        
        # Categorize holding times
        categories = {
            "very_short": [t for t in holding_times if t < 5],
            "short": [t for t in holding_times if 5 <= t < 30],
            "medium": [t for t in holding_times if 30 <= t < 120],
            "long": [t for t in holding_times if 120 <= t < 480],
            "very_long": [t for t in holding_times if t >= 480]
        }
        
        for category, times in categories.items():
            if len(times) >= min_occurrences:
                avg_time = sum(times) / len(times)
                patterns.append(Pattern(
                    pattern_id=f"holding_{category}",
                    pattern_type="holding_time",
                    description=f"{category.replace('_', ' ').title()} holding time",
                    frequency=len(times) / len(holding_times),
                    strength=avg_time,
                    last_occurrence=datetime.utcnow(),
                    first_occurrence=datetime.utcnow(),
                    occurrences=len(times),
                    metrics={
                        "avg_minutes": avg_time,
                        "min_minutes": min(times),
                        "max_minutes": max(times)
                    }
                ))
        
        return patterns
    
    def _generate_pattern_insights(self, patterns: List[Pattern]) -> List[str]:
        """
        Generate insights from detected patterns.
        
        Args:
            patterns: List of Pattern objects
            
        Returns:
            List of insight strings
        """
        insights = []
        
        # Group patterns by type
        streak_patterns = [p for p in patterns if p.pattern_type in ["winning_streak", "losing_streak"]]
        time_patterns = [p for p in patterns if p.pattern_type.startswith("time_")]
        pnl_patterns = [p for p in patterns if p.pattern_type.startswith("pnl_")]
        holding_patterns = [p for p in patterns if p.pattern_type == "holding_time"]
        
        # Streak insights
        for pattern in streak_patterns:
            if pattern.pattern_type == "winning_streak":
                insights.append(
                    f"Winning streaks: {pattern.occurrences} occurrences, "
                    f"avg length {pattern.metrics.get('average_length', 0):.1f} trades"
                )
            else:
                insights.append(
                    f"Losing streaks: {pattern.occurrences} occurrences, "
                    f"avg length {pattern.metrics.get('average_length', 0):.1f} trades"
                )
        
        # Time insights
        for pattern in time_patterns:
            if pattern.pattern_type == "time_hour":
                hour = int(pattern.pattern_id.split("_")[1])
                win_rate = pattern.metrics.get("win_rate", 0)
                insights.append(
                    f"Hour {hour}: {win_rate:.1%} win rate, "
                    f"avg P&L ${pattern.metrics.get('avg_pnl', 0):.2f}"
                )
        
        # P&L insights
        for pattern in pnl_patterns:
            if pattern.pattern_type == "pnl_positive":
                insights.append(
                    f"Winning trades: {pattern.occurrences}, "
                    f"avg ${pattern.metrics.get('avg_win', 0):.2f}"
                )
            else:
                insights.append(
                    f"Losing trades: {pattern.occurrences}, "
                    f"avg ${pattern.metrics.get('avg_loss', 0):.2f}"
                )
        
        return insights


# Global pattern detector instance
_pattern_detector: Optional[PatternDetector] = None


def get_pattern_detector() -> PatternDetector:
    """
    Get the global pattern detector instance.
    
    Returns:
        PatternDetector instance
    """
    global _pattern_detector
    if _pattern_detector is None:
        _pattern_detector = PatternDetector()
    return _pattern_detector
