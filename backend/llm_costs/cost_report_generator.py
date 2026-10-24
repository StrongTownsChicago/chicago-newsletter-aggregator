"""
Cost report generation and formatting.

Generates reports in multiple formats (text, JSON, CSV) for LLM cost analysis.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from llm_costs.cost_calculator import ModelPricing, calculate_cost
from llm_costs.newsletter_token_analyzer import (
    NewsletterTokenAnalysis,
    OperationTokens,
    WeeklyReportTokenAnalysis,
)
from shared.dates import CHICAGO_TIMEZONE


def generate_text_report(
    analyses: list[NewsletterTokenAnalysis],
    model_pricing: ModelPricing,
) -> str:
    """
    Generate human-readable text report.

    Args:
        analyses: List of newsletter token analyses
        model_pricing: Pricing information for the model

    Returns:
        Formatted text report as string
    """
    if not analyses:
        return "No newsletters analyzed."

    # Calculate aggregates
    topic_input = sum(a.topic_extraction.input_tokens for a in analyses)
    topic_output = sum(a.topic_extraction.output_tokens for a in analyses)
    summary_input = sum(a.summary_generation.input_tokens for a in analyses)
    summary_output = sum(a.summary_generation.output_tokens for a in analyses)

    total_input = topic_input + summary_input
    total_output = topic_output + summary_output

    # Calculate costs
    topic_cost = calculate_cost(topic_input, topic_output, model_pricing)
    summary_cost = calculate_cost(summary_input, summary_output, model_pricing)
    total_cost = calculate_cost(total_input, total_output, model_pricing)

    # Format report
    report = []
    report.append("=" * 65)
    report.append("LLM TOKEN COST ANALYSIS")
    report.append("=" * 65)
    report.append(
        f"Date: {datetime.now(CHICAGO_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}"
    )
    report.append(f"Newsletters Analyzed: {len(analyses)}")
    report.append(f"Model: {model_pricing.model} ({model_pricing.provider})")
    report.append(
        f"Pricing: ${model_pricing.input_cost_per_1m:.2f}/1M input, ${model_pricing.output_cost_per_1m:.2f}/1M output"
    )
    report.append("")
    report.append("-" * 65)
    report.append("NEWSLETTER PROCESSING (2 calls per newsletter)")
    report.append("-" * 65)
    report.append(
        f"{'Operation':<20} {'Input Tokens':>12} {'Output Tokens':>12} {'Cost':>10}"
    )
    report.append("-" * 65)
    report.append(
        f"{'Topic Extraction':<20} {topic_input:>12,} {topic_output:>12,} ${topic_cost['total_cost']:>9.4f}"
    )
    report.append(
        f"{'Summary Generation':<20} {summary_input:>12,} {summary_output:>12,} ${summary_cost['total_cost']:>9.4f}"
    )
    report.append("-" * 65)
    report.append(
        f"{'TOTAL':<20} {total_input:>12,} {total_output:>12,} ${total_cost['total_cost']:>9.4f}"
    )
    report.append("")
    report.append("-" * 65)
    report.append("COST BREAKDOWN PER NEWSLETTER")
    report.append("-" * 65)
    cost_per_newsletter = total_cost["total_cost"] / len(analyses)
    report.append(f"Average cost per newsletter: ${cost_per_newsletter:.4f}")
    report.append(
        f"Total cost for {len(analyses)} newsletters: ${total_cost['total_cost']:.4f}"
    )
    report.append("")
    report.append("-" * 65)
    report.append("PROJECTIONS")
    report.append("-" * 65)
    report.append(f"100 newsletters/month: ${cost_per_newsletter * 100:.2f}")
    report.append(f"1,000 newsletters/month: ${cost_per_newsletter * 1000:.2f}")
    report.append("=" * 65)

    return "\n".join(report)


def generate_json_report(
    analyses: list[NewsletterTokenAnalysis],
    model_pricing: ModelPricing,
) -> dict[str, Any]:
    """
    Generate structured JSON report.

    Args:
        analyses: List of newsletter token analyses
        model_pricing: Pricing information for the model

    Returns:
        Dict with complete analysis data
    """
    if not analyses:
        return {"error": "No newsletters analyzed"}

    # Calculate aggregates
    topic_input = sum(a.topic_extraction.input_tokens for a in analyses)
    topic_output = sum(a.topic_extraction.output_tokens for a in analyses)
    summary_input = sum(a.summary_generation.input_tokens for a in analyses)
    summary_output = sum(a.summary_generation.output_tokens for a in analyses)

    total_input = topic_input + summary_input
    total_output = topic_output + summary_output

    # Calculate costs
    topic_cost = calculate_cost(topic_input, topic_output, model_pricing)
    summary_cost = calculate_cost(summary_input, summary_output, model_pricing)
    total_cost = calculate_cost(total_input, total_output, model_pricing)

    cost_per_newsletter = total_cost["total_cost"] / len(analyses)

    return {
        "metadata": {
            "analysis_date": datetime.now(CHICAGO_TIMEZONE).isoformat(),
            "newsletter_count": len(analyses),
            "model": model_pricing.model,
            "provider": model_pricing.provider,
        },
        "pricing": {
            "input_cost_per_1m": model_pricing.input_cost_per_1m,
            "output_cost_per_1m": model_pricing.output_cost_per_1m,
        },
        "operations": {
            "topic_extraction": {
                "total_input_tokens": topic_input,
                "total_output_tokens": topic_output,
                "input_cost": topic_cost["input_cost"],
                "output_cost": topic_cost["output_cost"],
                "total_cost": topic_cost["total_cost"],
            },
            "summary_generation": {
                "total_input_tokens": summary_input,
                "total_output_tokens": summary_output,
                "input_cost": summary_cost["input_cost"],
                "output_cost": summary_cost["output_cost"],
                "total_cost": summary_cost["total_cost"],
            },
        },
        "totals": {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost": total_cost["total_cost"],
        },
        "per_newsletter": {
            "avg_input_tokens": total_input // len(analyses),
            "avg_output_tokens": total_output // len(analyses),
            "avg_cost": cost_per_newsletter,
        },
        "projections": {
            "monthly_100": cost_per_newsletter * 100,
            "monthly_1000": cost_per_newsletter * 1000,
        },
    }


def generate_csv_report(
    analyses: list[NewsletterTokenAnalysis],
    model_pricing: ModelPricing,
) -> str:
    """
    Generate CSV format report.

    Args:
        analyses: List of newsletter token analyses
        model_pricing: Pricing information for the model

    Returns:
        CSV formatted string
    """
    if not analyses:
        return (
            "operation,input_tokens,output_tokens,input_cost,output_cost,total_cost\n"
        )

    # Calculate aggregates
    topic_input = sum(a.topic_extraction.input_tokens for a in analyses)
    topic_output = sum(a.topic_extraction.output_tokens for a in analyses)
    summary_input = sum(a.summary_generation.input_tokens for a in analyses)
    summary_output = sum(a.summary_generation.output_tokens for a in analyses)

    # Calculate costs
    topic_cost = calculate_cost(topic_input, topic_output, model_pricing)
    summary_cost = calculate_cost(summary_input, summary_output, model_pricing)

    # Build CSV
    lines = [
        "operation,input_tokens,output_tokens,input_cost,output_cost,total_cost",
        f"topic_extraction,{topic_input},{topic_output},{topic_cost['input_cost']:.6f},{topic_cost['output_cost']:.6f},{topic_cost['total_cost']:.6f}",
        f"summary_generation,{summary_input},{summary_output},{summary_cost['input_cost']:.6f},{summary_cost['output_cost']:.6f},{summary_cost['total_cost']:.6f}",
    ]

    return "\n".join(lines) + "\n"


def generate_comparison_report(
    analyses_by_model: dict[str, list[NewsletterTokenAnalysis]],
    pricing_by_model: dict[str, ModelPricing],
) -> str:
    """
    Generate comparison report for multiple models.

    Args:
        analyses_by_model: Dict mapping model names to their analyses
        pricing_by_model: Dict mapping model names to their pricing

    Returns:
        Formatted comparison report
    """
    if not analyses_by_model:
        return "No analyses to compare."

    # Calculate costs for each model
    model_costs = {}
    for model_name, analyses in analyses_by_model.items():
        pricing = pricing_by_model[model_name]
        total_input = sum(a.total_input_tokens for a in analyses)
        total_output = sum(a.total_output_tokens for a in analyses)
        cost = calculate_cost(total_input, total_output, pricing)
        model_costs[model_name] = {
            "total_tokens": total_input + total_output,
            "total_cost": cost["total_cost"],
            "cost_per_newsletter": cost["total_cost"] / len(analyses),
        }

    # Sort by cost
    sorted_models = sorted(model_costs.items(), key=lambda x: x[1]["total_cost"])

    # Format report
    newsletter_count = len(next(iter(analyses_by_model.values())))
    report = []
    report.append("=" * 75)
    report.append(f"MODEL COST COMPARISON ({newsletter_count} newsletters)")
    report.append("=" * 75)
    report.append("")
    report.append(
        f"{'Model':<25} {'Total Tokens':>15} {'Total Cost':>12} {'Cost/Newsletter':>15}"
    )
    report.append("-" * 75)

    for model_name, costs in sorted_models:
        report.append(
            f"{model_name:<25} {costs['total_tokens']:>15,} ${costs['total_cost']:>11.4f} ${costs['cost_per_newsletter']:>14.4f}"
        )

    report.append("")
    report.append(
        f"Cheapest: {sorted_models[0][0]} (${sorted_models[0][1]['total_cost']:.4f})"
    )
    report.append(
        f"Most Expensive: {sorted_models[-1][0]} (${sorted_models[-1][1]['total_cost']:.4f})"
    )

    if len(sorted_models) > 1:
        cost_ratio = (
            sorted_models[-1][1]["total_cost"] / sorted_models[0][1]["total_cost"]
        )
        report.append(f"Cost Variance: {cost_ratio:.1f}x")

    report.append("=" * 75)

    return "\n".join(report)


COMBINED_RULE_WIDTH = 65
WEEKS_PER_MONTH = 4


@dataclass(frozen=True)
class TokenTotals:
    """Input and output tokens summed over one or more LLM calls."""

    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "TokenTotals") -> "TokenTotals":
        return TokenTotals(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
        )


def sum_operation_tokens(operations: Iterable[OperationTokens]) -> TokenTotals:
    """Total tokens across operations."""
    return sum(
        (TokenTotals(op.input_tokens, op.output_tokens) for op in operations),
        TokenTotals(),
    )


def total_cost(tokens: TokenTotals, model_pricing: ModelPricing) -> float:
    """Dollar cost of the summed tokens (priced once, not summed per call)."""
    return calculate_cost(tokens.input_tokens, tokens.output_tokens, model_pricing)[
        "total_cost"
    ]


def format_cost_row(
    label: str, tokens: TokenTotals, model_pricing: ModelPricing
) -> str:
    cost = total_cost(tokens, model_pricing)
    return f"{label:<20} {tokens.input_tokens:>12,} {tokens.output_tokens:>12,} ${cost:>9.4f}"


def section_heading(title: str) -> list[str]:
    rule = "-" * COMBINED_RULE_WIDTH
    return [rule, title, rule]


def cost_table(
    title: str, rows: list[tuple[str, TokenTotals]], model_pricing: ModelPricing
) -> list[str]:
    """A titled table of cost rows followed by a subtotal of all of them."""
    subtotal = sum((tokens for _, tokens in rows), TokenTotals())
    return [
        *section_heading(title),
        f"{'Operation':<20} {'Input Tokens':>12} {'Output Tokens':>12} {'Cost':>10}",
        "-" * COMBINED_RULE_WIDTH,
        *(format_cost_row(label, tokens, model_pricing) for label, tokens in rows),
        "-" * COMBINED_RULE_WIDTH,
        format_cost_row("SUBTOTAL", subtotal, model_pricing),
        "",
    ]


def combined_report_header(
    newsletter_count: int, weekly_report_count: int, model_pricing: ModelPricing
) -> list[str]:
    return [
        "=" * COMBINED_RULE_WIDTH,
        "LLM TOKEN COST ANALYSIS (NEWSLETTER + WEEKLY REPORTS)",
        "=" * COMBINED_RULE_WIDTH,
        f"Date: {datetime.now(CHICAGO_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}",
        f"Newsletters Analyzed: {newsletter_count}",
        f"Weekly Reports Generated: {weekly_report_count}",
        f"Model: {model_pricing.model} ({model_pricing.provider})",
        f"Pricing: ${model_pricing.input_cost_per_1m:.2f}/1M input, ${model_pricing.output_cost_per_1m:.2f}/1M output",
        "",
    ]


def weekly_projection_lines(
    weekly_analyses: list[WeeklyReportTokenAnalysis],
    weekly_cost_per_report: float,
    newsletter_cost: float,
) -> list[str]:
    """Monthly weekly-report cost, assuming each month repeats the average week."""
    weeks = max(len({a.week_id for a in weekly_analyses}), 1)
    monthly_weekly_reports = len(weekly_analyses) / weeks * WEEKS_PER_MONTH
    monthly_weekly_cost = weekly_cost_per_report * monthly_weekly_reports
    return [
        "",
        f"~{monthly_weekly_reports:.0f} weekly reports/month: ${monthly_weekly_cost:.2f}",
        f"100 newsletters + weekly reports: ${newsletter_cost * 100 + monthly_weekly_cost:.2f}",
        f"1,000 newsletters + weekly reports: ${newsletter_cost * 1000 + monthly_weekly_cost:.2f}",
    ]


def combined_cost_summary(
    newsletter_count: int,
    newsletter_tokens: TokenTotals,
    weekly_analyses: list[WeeklyReportTokenAnalysis],
    weekly_tokens: TokenTotals,
    model_pricing: ModelPricing,
) -> list[str]:
    """The cost breakdown and monthly projection sections."""
    newsletter_total = total_cost(newsletter_tokens, model_pricing)
    newsletter_cost = newsletter_total / newsletter_count
    lines = [
        *section_heading("COST BREAKDOWN"),
        f"Per newsletter (processing only): ${newsletter_cost:.4f}",
    ]

    weekly_count = len(weekly_analyses)
    if weekly_analyses:
        weekly_cost_per_report = total_cost(weekly_tokens, model_pricing) / weekly_count
        grand_cost = total_cost(newsletter_tokens + weekly_tokens, model_pricing)
        lines += [
            f"Per weekly report: ${weekly_cost_per_report:.4f}",
            f"Total for {newsletter_count} newsletters + {weekly_count} reports: ${grand_cost:.4f}",
        ]
    else:
        lines.append(
            f"Total for {newsletter_count} newsletters: ${newsletter_total:.4f}"
        )

    lines += [
        "",
        *section_heading("MONTHLY PROJECTIONS"),
        f"100 newsletters/month (processing only): ${newsletter_cost * 100:.2f}",
        f"1,000 newsletters/month (processing only): ${newsletter_cost * 1000:.2f}",
    ]
    if weekly_analyses:
        lines += weekly_projection_lines(
            weekly_analyses, weekly_cost_per_report, newsletter_cost
        )
    return lines


def generate_combined_text_report(
    newsletter_analyses: list[NewsletterTokenAnalysis],
    weekly_analyses: list[WeeklyReportTokenAnalysis],
    model_pricing: ModelPricing,
) -> str:
    """
    Format a text report of newsletter and weekly report costs for one model.

    Returns "No newsletters analyzed." when newsletter_analyses is empty.
    """
    if not newsletter_analyses:
        return "No newsletters analyzed."

    topic_tokens = sum_operation_tokens(a.topic_extraction for a in newsletter_analyses)
    summary_tokens = sum_operation_tokens(
        a.summary_generation for a in newsletter_analyses
    )
    phase1_tokens = sum_operation_tokens(
        op for a in weekly_analyses for op in a.phase1_operations
    )
    phase2_tokens = sum_operation_tokens(a.phase2_operation for a in weekly_analyses)
    newsletter_tokens = topic_tokens + summary_tokens
    weekly_tokens = phase1_tokens + phase2_tokens

    report = combined_report_header(
        len(newsletter_analyses), len(weekly_analyses), model_pricing
    )
    report += cost_table(
        "NEWSLETTER PROCESSING (2 calls per newsletter)",
        [("Topic Extraction", topic_tokens), ("Summary Generation", summary_tokens)],
        model_pricing,
    )
    if weekly_analyses:
        report += cost_table(
            f"WEEKLY REPORT SYNTHESIS ({len(weekly_analyses)} topic reports)",
            [
                ("Phase 1: Extract", phase1_tokens),
                ("Phase 2: Synthesize", phase2_tokens),
            ],
            model_pricing,
        )
    report += [
        *section_heading("GRAND TOTAL (Newsletter + Weekly)"),
        format_cost_row("TOTAL", newsletter_tokens + weekly_tokens, model_pricing),
        "",
    ]
    report += combined_cost_summary(
        len(newsletter_analyses),
        newsletter_tokens,
        weekly_analyses,
        weekly_tokens,
        model_pricing,
    )
    report.append("=" * COMBINED_RULE_WIDTH)

    return "\n".join(report)
