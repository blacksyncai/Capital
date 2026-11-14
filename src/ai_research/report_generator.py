"""
Report Generator

Generates comprehensive reports for strategy analysis and research.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any
import logging
import json

from .data_analyzer import DataAnalyzer, AnalysisResult
from .pattern_detector import PatternDetector, PatternDetectionResult


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Report:
    """Represents a generated report."""
    report_id: str
    report_type: str
    title: str
    timestamp: datetime
    summary: str
    sections: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ReportGenerator:
    """
    Generates comprehensive reports for strategy analysis.
    
    Report types:
    - Strategy performance report
    - Pattern analysis report
    - Strategy comparison report
    - Execution quality report
    - Comprehensive research report
    """
    
    def __init__(self):
        """Initialize the report generator."""
        self.logger = logger
        self.data_analyzer = DataAnalyzer()
        self.pattern_detector = PatternDetector()
    
    def generate_strategy_report(
        self,
        strategy_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Report:
        """
        Generate a strategy performance report.
        
        Args:
            strategy_id: Strategy identifier
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Report object
        """
        report = Report(
            report_id=f"report_strategy_{strategy_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            report_type="strategy_performance",
            title=f"Strategy Performance Report: {strategy_id}",
            timestamp=datetime.utcnow()
        )
        
        try:
            # Analyze performance
            analysis = self.data_analyzer.analyze_strategy_performance(
                strategy_id, start_date, end_date
            )
            
            # Add to report
            report.sections["performance_analysis"] = analysis.to_dict()
            
            # Detect patterns
            patterns = self.pattern_detector.detect_all_patterns(
                strategy_id, start_date, end_date
            )
            report.sections["pattern_analysis"] = patterns.to_dict()
            
            # Generate summary
            report.summary = self._generate_strategy_summary(analysis, patterns)
            
            # Generate recommendations
            report.recommendations = self._generate_strategy_recommendations(analysis, patterns)
            
            # Add warnings
            report.warnings = analysis.warnings + patterns.warnings
            
        except Exception as e:
            self.logger.error(f"Error generating strategy report: {e}")
            report.warnings.append(f"Error generating report: {e}")
        
        return report
    
    def generate_comparison_report(
        self,
        strategy_ids: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Report:
        """
        Generate a strategy comparison report.
        
        Args:
            strategy_ids: List of strategy identifiers
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Report object
        """
        report = Report(
            report_id=f"report_comparison_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            report_type="strategy_comparison",
            title=f"Strategy Comparison Report: {', '.join(strategy_ids)}",
            timestamp=datetime.utcnow()
        )
        
        try:
            # Analyze each strategy
            analyses = {}
            for strategy_id in strategy_ids:
                analysis = self.data_analyzer.analyze_strategy_performance(
                    strategy_id, start_date, end_date
                )
                analyses[strategy_id] = analysis
            
            # Compare strategies
            comparisons = self.data_analyzer.compare_strategies(
                strategy_ids, start_date=start_date, end_date=end_date
            )
            
            # Add to report
            report.sections["individual_analyses"] = {
                sid: a.to_dict() for sid, a in analyses.items()
            }
            report.sections["comparisons"] = [
                self._comparison_to_dict(c) for c in comparisons
            ]
            
            # Generate summary
            report.summary = self._generate_comparison_summary(analyses, comparisons)
            
            # Generate recommendations
            report.recommendations = self._generate_comparison_recommendations(comparisons)
            
        except Exception as e:
            self.logger.error(f"Error generating comparison report: {e}")
            report.warnings.append(f"Error generating report: {e}")
        
        return report
    
    def generate_pattern_report(
        self,
        strategy_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Report:
        """
        Generate a pattern analysis report.
        
        Args:
            strategy_id: Optional strategy filter
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Report object
        """
        report = Report(
            report_id=f"report_patterns_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            report_type="pattern_analysis",
            title="Pattern Analysis Report",
            timestamp=datetime.utcnow()
        )
        
        try:
            # Detect patterns
            patterns = self.pattern_detector.detect_all_patterns(
                strategy_id, start_date, end_date
            )
            
            # Add to report
            report.sections["pattern_detection"] = patterns.to_dict()
            
            # Generate summary
            report.summary = self._generate_pattern_summary(patterns)
            
            # Generate recommendations
            report.recommendations = self._generate_pattern_recommendations(patterns)
            
            # Add warnings
            report.warnings = patterns.warnings
            
        except Exception as e:
            self.logger.error(f"Error generating pattern report: {e}")
            report.warnings.append(f"Error generating report: {e}")
        
        return report
    
    def generate_execution_report(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Report:
        """
        Generate an execution quality report.
        
        Args:
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Report object
        """
        report = Report(
            report_id=f"report_execution_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            report_type="execution_quality",
            title="Execution Quality Report",
            timestamp=datetime.utcnow()
        )
        
        try:
            # Analyze execution quality
            analysis = self.data_analyzer.analyze_execution_quality(start_date, end_date)
            
            # Add to report
            report.sections["execution_analysis"] = analysis.to_dict()
            
            # Generate summary
            report.summary = self._generate_execution_summary(analysis)
            
            # Generate recommendations
            report.recommendations = self._generate_execution_recommendations(analysis)
            
            # Add warnings
            report.warnings = analysis.warnings
            
        except Exception as e:
            self.logger.error(f"Error generating execution report: {e}")
            report.warnings.append(f"Error generating report: {e}")
        
        return report
    
    def generate_comprehensive_report(
        self,
        strategy_ids: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Report:
        """
        Generate a comprehensive research report.
        
        Args:
            strategy_ids: List of strategy identifiers
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Report object
        """
        report = Report(
            report_id=f"report_comprehensive_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            report_type="comprehensive",
            title="Comprehensive Research Report",
            timestamp=datetime.utcnow()
        )
        
        try:
            # Generate all sub-reports
            strategy_reports = {}
            for strategy_id in strategy_ids:
                strat_report = self.generate_strategy_report(
                    strategy_id, start_date, end_date
                )
                strategy_reports[strategy_id] = strat_report.to_dict()
            
            comparison_report = self.generate_comparison_report(
                strategy_ids, start_date, end_date
            )
            
            pattern_report = self.generate_pattern_report(
                start_date=start_date, end_date=end_date
            )
            
            execution_report = self.generate_execution_report(
                start_date, end_date
            )
            
            # Add to report
            report.sections["strategy_reports"] = strategy_reports
            report.sections["comparison_report"] = comparison_report.to_dict()
            report.sections["pattern_report"] = pattern_report.to_dict()
            report.sections["execution_report"] = execution_report.to_dict()
            
            # Generate comprehensive summary
            report.summary = self._generate_comprehensive_summary(
                strategy_reports, comparison_report, pattern_report, execution_report
            )
            
            # Generate comprehensive recommendations
            report.recommendations = self._generate_comprehensive_recommendations(
                strategy_reports, comparison_report, pattern_report, execution_report
            )
            
            # Collect all warnings
            for strat_report in strategy_reports.values():
                report.warnings.extend(strat_report.get("warnings", []))
            report.warnings.extend(comparison_report.warnings)
            report.warnings.extend(pattern_report.warnings)
            report.warnings.extend(execution_report.warnings)
            
        except Exception as e:
            self.logger.error(f"Error generating comprehensive report: {e}")
            report.warnings.append(f"Error generating report: {e}")
        
        return report
    
    def format_report(self, report: Report, format_type: str = "text") -> str:
        """
        Format a report in a specific format.
        
        Args:
            report: Report object
            format_type: Format type (text, html, json, markdown)
            
        Returns:
            Formatted report string
        """
        if format_type == "json":
            return self._format_as_json(report)
        elif format_type == "html":
            return self._format_as_html(report)
        elif format_type == "markdown":
            return self._format_as_markdown(report)
        else:
            return self._format_as_text(report)
    
    def _generate_strategy_summary(
        self,
        analysis: AnalysisResult,
        patterns: PatternDetectionResult
    ) -> str:
        """Generate summary for strategy report."""
        metrics = analysis.metrics
        
        summary = f"Strategy Performance Summary\n"
        summary += f"=" * 40 + "\n\n"
        summary += f"Total Trades: {metrics.get('total_cycles', 0)}\n"
        summary += f"Completed Trades: {metrics.get('completed_cycles', 0)}\n"
        summary += f"Net P&L: ${metrics.get('net_pnl', 0):.2f}\n"
        summary += f"Win Rate: {metrics.get('win_rate', 0):.1%}\n"
        summary += f"Profit Factor: {metrics.get('profit_factor', 0):.2f}\n"
        summary += f"Max Drawdown: ${metrics.get('max_drawdown', 0):.2f} ({metrics.get('max_drawdown_percent', 0):.1f}%)\n"
        summary += f"Average Holding Time: {metrics.get('avg_holding_time_minutes', 0):.0f} minutes\n\n"
        
        if patterns.patterns:
            summary += f"Detected Patterns: {len(patterns.patterns)}\n"
            for pattern in patterns.patterns[:5]:  # Top 5 patterns
                summary += f"  - {pattern.description}: {pattern.occurrences} occurrences\n"
        
        return summary
    
    def _generate_strategy_recommendations(
        self,
        analysis: AnalysisResult,
        patterns: PatternDetectionResult
    ) -> List[str]:
        """Generate recommendations for strategy report."""
        recommendations = []
        metrics = analysis.metrics
        
        # Performance-based recommendations
        win_rate = metrics.get("win_rate", 0)
        if win_rate < 0.5:
            recommendations.append(
                "Win rate is below 50%. Consider improving entry conditions or "
                "reducing position sizes."
            )
        
        profit_factor = metrics.get("profit_factor", 0)
        if profit_factor < 1:
            recommendations.append(
                "Profit factor is below 1. Losing trades are larger than winning trades. "
                "Consider adjusting stop loss and take profit levels."
            )
        
        max_drawdown = metrics.get("max_drawdown_percent", 0)
        if max_drawdown > 20:
            recommendations.append(
                f"Max drawdown is {max_drawdown:.1f}%. Consider implementing stricter "
                "risk management."
            )
        
        # Pattern-based recommendations
        for pattern in patterns.patterns:
            if pattern.pattern_type == "losing_streak" and pattern.occurrences > 2:
                recommendations.append(
                    f"Losing streaks detected ({pattern.occurrences} occurrences). "
                    "Consider reducing position sizes during losing streaks."
                )
        
        return recommendations
    
    def _generate_comparison_summary(
        self,
        analyses: Dict[str, AnalysisResult],
        comparisons: List[Any]
    ) -> str:
        """Generate summary for comparison report."""
        summary = "Strategy Comparison Summary\n"
        summary += "=" * 40 + "\n\n"
        
        for strategy_id, analysis in analyses.items():
            metrics = analysis.metrics
            summary += f"{strategy_id}:\n"
            summary += f"  Net P&L: ${metrics.get('net_pnl', 0):.2f}\n"
            summary += f"  Win Rate: {metrics.get('win_rate', 0):.1%}\n"
            summary += f"  Profit Factor: {metrics.get('profit_factor', 0):.2f}\n\n"
        
        if comparisons:
            summary += "Key Comparisons:\n"
            for comp in comparisons[:5]:  # Top 5 comparisons
                summary += f"  {comp.strategy_a_id} vs {comp.strategy_b_id} ({comp.metric}): "
                if comp.winner:
                    summary += f"{comp.winner} wins"
                else:
                    summary += "Tie"
                summary += f" (difference: {comp.difference:.4f})\n"
        
        return summary
    
    def _generate_comparison_recommendations(self, comparisons: List[Any]) -> List[str]:
        """Generate recommendations for comparison report."""
        recommendations = []
        
        # Find best strategy for each metric
        best_by_metric = {}
        for comp in comparisons:
            if comp.winner:
                if comp.metric not in best_by_metric:
                    best_by_metric[comp.metric] = {}
                if comp.winner not in best_by_metric[comp.metric]:
                    best_by_metric[comp.metric][comp.winner] = 0
                best_by_metric[comp.metric][comp.winner] += 1
        
        for metric, winners in best_by_metric.items():
            best_strategy = max(winners, key=winners.get)
            recommendations.append(
                f"{best_strategy} performs best on {metric}. "
                "Consider allocating more capital to this strategy."
            )
        
        return recommendations
    
    def _generate_pattern_summary(self, patterns: PatternDetectionResult) -> str:
        """Generate summary for pattern report."""
        summary = "Pattern Analysis Summary\n"
        summary += "=" * 40 + "\n\n"
        summary += f"Total Patterns Detected: {len(patterns.patterns)}\n\n"
        
        # Group by type
        by_type = {}
        for pattern in patterns.patterns:
            if pattern.pattern_type not in by_type:
                by_type[pattern.pattern_type] = []
            by_type[pattern.pattern_type].append(pattern)
        
        for pattern_type, type_patterns in by_type.items():
            summary += f"{pattern_type}: {len(type_patterns)} patterns\n"
            for pattern in type_patterns[:3]:  # Top 3 per type
                summary += f"  - {pattern.description}: {pattern.occurrences} occurrences\n"
        
        return summary
    
    def _generate_pattern_recommendations(self, patterns: PatternDetectionResult) -> List[str]:
        """Generate recommendations for pattern report."""
        recommendations = []
        
        for pattern in patterns.patterns:
            if pattern.pattern_type == "losing_streak":
                recommendations.append(
                    f"Losing streaks of {pattern.metrics.get('average_length', 0):.0f} trades "
                    f"occur {pattern.frequency:.1%} of the time. "
                    "Consider reducing position sizes during these periods."
                )
            elif pattern.pattern_type == "winning_streak":
                recommendations.append(
                    f"Winning streaks of {pattern.metrics.get('average_length', 0):.0f} trades "
                    f"occur {pattern.frequency:.1%} of the time. "
                    "Consider increasing position sizes during these periods."
                )
            elif pattern.pattern_type == "time_hour":
                hour = int(pattern.pattern_id.split("_")[1])
                win_rate = pattern.metrics.get("win_rate", 0)
                if win_rate > 0.6:
                    recommendations.append(
                        f"Hour {hour}:00 has a high win rate ({win_rate:.1%}). "
                        "Consider trading more during this hour."
                    )
                elif win_rate < 0.4:
                    recommendations.append(
                        f"Hour {hour}:00 has a low win rate ({win_rate:.1%}). "
                        "Consider avoiding trading during this hour."
                    )
        
        return recommendations
    
    def _generate_execution_summary(self, analysis: AnalysisResult) -> str:
        """Generate summary for execution report."""
        metrics = analysis.metrics
        
        summary = "Execution Quality Summary\n"
        summary += "=" * 40 + "\n\n"
        summary += f"Average Slippage: {metrics.get('avg_slippage', 0):.2f} points\n"
        summary += f"Max Slippage: {metrics.get('max_slippage', 0):.2f} points\n"
        summary += f"Total Commission: ${metrics.get('total_commission', 0):.2f}\n"
        summary += f"Total Swap: ${metrics.get('total_swap', 0):.2f}\n\n"
        
        return summary
    
    def _generate_execution_recommendations(self, analysis: AnalysisResult) -> List[str]:
        """Generate recommendations for execution report."""
        recommendations = []
        metrics = analysis.metrics
        
        avg_slippage = metrics.get("avg_slippage", 0)
        if avg_slippage > 1:
            recommendations.append(
                f"Average slippage is {avg_slippage:.2f} points. "
                "Consider using limit orders or waiting for better liquidity."
            )
        
        total_commission = metrics.get("total_commission", 0)
        if total_commission > 10:
            recommendations.append(
                f"High commission costs: ${total_commission:.2f}. "
                "Consider negotiating lower commissions or trading larger sizes."
            )
        
        return recommendations
    
    def _generate_comprehensive_summary(
        self,
        strategy_reports: Dict[str, Dict],
        comparison_report: Report,
        pattern_report: Report,
        execution_report: Report
    ) -> str:
        """Generate comprehensive summary."""
        summary = "Comprehensive Research Report Summary\n"
        summary += "=" * 40 + "\n\n"
        
        summary += "Strategy Performance:\n"
        for strategy_id, report in strategy_reports.items():
            metrics = report.get("sections", {}).get("performance_analysis", {}).get("metrics", {})
            summary += f"  {strategy_id}: Net P&L ${metrics.get('net_pnl', 0):.2f}, "
            summary += f"Win Rate {metrics.get('win_rate', 0):.1%}\n"
        
        summary += "\nComparisons:\n"
        comparisons = comparison_report.sections.get("comparisons", [])
        for comp in comparisons[:3]:
            summary += f"  {comp['strategy_a_id']} vs {comp['strategy_b_id']}: "
            if comp.get("winner"):
                summary += f"{comp['winner']} wins on {comp['metric']}\n"
        
        summary += "\nPatterns:\n"
        patterns = pattern_report.sections.get("pattern_detection", {}).get("patterns", [])
        summary += f"  {len(patterns)} patterns detected\n"
        
        summary += "\nExecution:\n"
        exec_metrics = execution_report.sections.get("execution_analysis", {}).get("metrics", {})
        summary += f"  Avg Slippage: {exec_metrics.get('avg_slippage', 0):.2f} points\n"
        
        return summary
    
    def _generate_comprehensive_recommendations(
        self,
        strategy_reports: Dict[str, Dict],
        comparison_report: Report,
        pattern_report: Report,
        execution_report: Report
    ) -> List[str]:
        """Generate comprehensive recommendations."""
        recommendations = []
        
        # From strategy reports
        for strategy_id, report in strategy_reports.items():
            recs = report.get("recommendations", [])
            for rec in recs:
                recommendations.append(f"[{strategy_id}] {rec}")
        
        # From comparison report
        recommendations.extend(comparison_report.recommendations)
        
        # From pattern report
        recommendations.extend(pattern_report.recommendations)
        
        # From execution report
        recommendations.extend(execution_report.recommendations)
        
        return recommendations
    
    def _format_as_json(self, report: Report) -> str:
        """Format report as JSON."""
        return json.dumps(report.to_dict(), indent=2)
    
    def _format_as_text(self, report: Report) -> str:
        """Format report as plain text."""
        text = f"{'=' * 60}\n"
        text += f"{report.title}\n"
        text += f"{'=' * 60}\n\n"
        text += f"Generated: {report.timestamp.isoformat()}\n"
        text += f"Report ID: {report.report_id}\n\n"
        
        text += f"{'-' * 60}\n"
        text += "SUMMARY\n"
        text += f"{'-' * 60}\n"
        text += report.summary + "\n\n"
        
        for section_name, section_data in report.sections.items():
            text += f"{'-' * 60}\n"
            text += f"{section_name.upper()}\n"
            text += f"{'-' * 60}\n"
            text += json.dumps(section_data, indent=2) + "\n\n"
        
        if report.recommendations:
            text += f"{'-' * 60}\n"
            text += "RECOMMENDATIONS\n"
            text += f"{'-' * 60}\n"
            for i, rec in enumerate(report.recommendations, 1):
                text += f"{i}. {rec}\n"
            text += "\n"
        
        if report.warnings:
            text += f"{'-' * 60}\n"
            text += "WARNINGS\n"
            text += f"{'-' * 60}\n"
            for warning in report.warnings:
                text += f"- {warning}\n"
        
        return text
    
    def _format_as_html(self, report: Report) -> str:
        """Format report as HTML."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{report.title}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }}
                h1 {{ color: #333; border-bottom: 2px solid #333; padding-bottom: 10px; }}
                h2 {{ color: #555; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
                .section {{ margin: 20px 0; }}
                .recommendation {{ background: #f0f8ff; padding: 10px; margin: 10px 0; border-left: 4px solid #007bff; }}
                .warning {{ background: #fff0f0; padding: 10px; margin: 10px 0; border-left: 4px solid #ff0000; }}
                pre {{ background: #f5f5f5; padding: 10px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <h1>{report.title}</h1>
            <p>Generated: {report.timestamp.isoformat()}</p>
            <p>Report ID: {report.report_id}</p>
            
            <div class="section">
                <h2>Summary</h2>
                <pre>{report.summary}</pre>
            </div>
        """
        
        for section_name, section_data in report.sections.items():
            html += f"""
            <div class="section">
                <h2>{section_name.replace('_', ' ').title()}</h2>
                <pre>{json.dumps(section_data, indent=2)}</pre>
            </div>
            """
        
        if report.recommendations:
            html += """
            <div class="section">
                <h2>Recommendations</h2>
            """
            for rec in report.recommendations:
                html += f'<div class="recommendation">{rec}</div>'
            html += "</div>"
        
        if report.warnings:
            html += """
            <div class="section">
                <h2>Warnings</h2>
            """
            for warning in report.warnings:
                html += f'<div class="warning">{warning}</div>'
            html += "</div>"
        
        html += "</body></html>"
        return html
    
    def _format_as_markdown(self, report: Report) -> str:
        """Format report as Markdown."""
        md = f"# {report.title}\n\n"
        md += f"**Generated:** {report.timestamp.isoformat()}\n\n"
        md += f"**Report ID:** {report.report_id}\n\n"
        
        md += "## Summary\n\n"
        md += f"```\n{report.summary}\n```\n\n"
        
        for section_name, section_data in report.sections.items():
            md += f"## {section_name.replace('_', ' ').title()}\n\n"
            md += f"```json\n{json.dumps(section_data, indent=2)}\n```\n\n"
        
        if report.recommendations:
            md += "## Recommendations\n\n"
            for i, rec in enumerate(report.recommendations, 1):
                md += f"{i}. {rec}\n"
            md += "\n"
        
        if report.warnings:
            md += "## Warnings\n\n"
            for warning in report.warnings:
                md += f"- {warning}\n"
        
        return md
    
    def _comparison_to_dict(self, comparison: Any) -> Dict[str, Any]:
        """Convert comparison to dictionary."""
        return {
            "strategy_a_id": comparison.strategy_a_id,
            "strategy_b_id": comparison.strategy_b_id,
            "metric": comparison.metric,
            "value_a": comparison.value_a,
            "value_b": comparison.value_b,
            "difference": comparison.difference,
            "significance": comparison.significance,
            "winner": comparison.winner
        }


# Global report generator instance
_report_generator: Optional[ReportGenerator] = None


def get_report_generator() -> ReportGenerator:
    """
    Get the global report generator instance.
    
    Returns:
        ReportGenerator instance
    """
    global _report_generator
    if _report_generator is None:
        _report_generator = ReportGenerator()
    return _report_generator
