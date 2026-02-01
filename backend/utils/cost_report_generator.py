"""
Cost report generation and formatting.

Generates reports in multiple formats (text, JSON, CSV) for LLM cost analysis.
"""

from dataclasses import dataclass
from typing import Any
from datetime import datetime

from utils.newsletter_token_analyzer import (
    NewsletterTokenAnalysis,
    WeeklyReportTokenAnalysis,
)
from utils.cost_calculator import ModelPricing, calculate_cost


@dataclass
class CostAnalysisReport:
    """Complete cost analysis for a set of newsletters."""

    metadata: dict[str, Any]
    pricing: dict[str, float]
    operations: dict[str, dict[str, float]]
    totals: dict[str, Any]
    per_newsletter: dict[str, float]
    projections: dict[str, float]


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
    relevance_input = sum(a.relevance_scoring.input_tokens for a in analyses)
    relevance_output = sum(a.relevance_scoring.output_tokens for a in analyses)

    total_input = topic_input + summary_input + relevance_input
    total_output = topic_output + summary_output + relevance_output

    # Calculate costs
    topic_cost = calculate_cost(topic_input, topic_output, model_pricing)
    summary_cost = calculate_cost(summary_input, summary_output, model_pricing)
    relevance_cost = calculate_cost(relevance_input, relevance_output, model_pricing)
    total_cost = calculate_cost(total_input, total_output, model_pricing)

    # Format report
    report = []
    report.append("=" * 65)
    report.append("LLM TOKEN COST ANALYSIS")
    report.append("=" * 65)
    report.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Newsletters Analyzed: {len(analyses)}")
    report.append(f"Model: {model_pricing.model} ({model_pricing.provider})")
    report.append(
        f"Pricing: ${model_pricing.input_cost_per_1m:.2f}/1M input, ${model_pricing.output_cost_per_1m:.2f}/1M output"
    )
    report.append("")
    report.append("-" * 65)
    report.append("NEWSLETTER PROCESSING (3 calls per newsletter)")
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
    report.append(
        f"{'Relevance Scoring':<20} {relevance_input:>12,} {relevance_output:>12,} ${relevance_cost['total_cost']:>9.4f}"
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
    relevance_input = sum(a.relevance_scoring.input_tokens for a in analyses)
    relevance_output = sum(a.relevance_scoring.output_tokens for a in analyses)

    total_input = topic_input + summary_input + relevance_input
    total_output = topic_output + summary_output + relevance_output

    # Calculate costs
    topic_cost = calculate_cost(topic_input, topic_output, model_pricing)
    summary_cost = calculate_cost(summary_input, summary_output, model_pricing)
    relevance_cost = calculate_cost(relevance_input, relevance_output, model_pricing)
    total_cost = calculate_cost(total_input, total_output, model_pricing)

    cost_per_newsletter = total_cost["total_cost"] / len(analyses)

    return {
        "metadata": {
            "analysis_date": datetime.now().isoformat(),
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
            "relevance_scoring": {
                "total_input_tokens": relevance_input,
                "total_output_tokens": relevance_output,
                "input_cost": relevance_cost["input_cost"],
                "output_cost": relevance_cost["output_cost"],
                "total_cost": relevance_cost["total_cost"],
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
    relevance_input = sum(a.relevance_scoring.input_tokens for a in analyses)
    relevance_output = sum(a.relevance_scoring.output_tokens for a in analyses)

    # Calculate costs
    topic_cost = calculate_cost(topic_input, topic_output, model_pricing)
    summary_cost = calculate_cost(summary_input, summary_output, model_pricing)
    relevance_cost = calculate_cost(relevance_input, relevance_output, model_pricing)

    # Build CSV
    lines = [
        "operation,input_tokens,output_tokens,input_cost,output_cost,total_cost",
        f"topic_extraction,{topic_input},{topic_output},{topic_cost['input_cost']:.6f},{topic_cost['output_cost']:.6f},{topic_cost['total_cost']:.6f}",
        f"summary_generation,{summary_input},{summary_output},{summary_cost['input_cost']:.6f},{summary_cost['output_cost']:.6f},{summary_cost['total_cost']:.6f}",
        f"relevance_scoring,{relevance_input},{relevance_output},{relevance_cost['input_cost']:.6f},{relevance_cost['output_cost']:.6f},{relevance_cost['total_cost']:.6f}",
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
    newsletter_count = len(list(analyses_by_model.values())[0])
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


def generate_combined_text_report(
    newsletter_analyses: list[NewsletterTokenAnalysis],
    weekly_analyses: list[WeeklyReportTokenAnalysis],
    model_pricing: ModelPricing,
) -> str:
    """
    Generate combined text report including both newsletter and weekly costs.

    Args:
        newsletter_analyses: List of newsletter token analyses
        weekly_analyses: List of weekly report token analyses
        model_pricing: Pricing information for the model

    Returns:
        Formatted text report with newsletter and weekly costs
    """
    if not newsletter_analyses:
        return "No newsletters analyzed."

    # Newsletter processing costs
    topic_input = sum(a.topic_extraction.input_tokens for a in newsletter_analyses)
    topic_output = sum(a.topic_extraction.output_tokens for a in newsletter_analyses)
    summary_input = sum(a.summary_generation.input_tokens for a in newsletter_analyses)
    summary_output = sum(
        a.summary_generation.output_tokens for a in newsletter_analyses
    )
    relevance_input = sum(a.relevance_scoring.input_tokens for a in newsletter_analyses)
    relevance_output = sum(
        a.relevance_scoring.output_tokens for a in newsletter_analyses
    )

    nl_total_input = topic_input + summary_input + relevance_input
    nl_total_output = topic_output + summary_output + relevance_output

    topic_cost = calculate_cost(topic_input, topic_output, model_pricing)
    summary_cost = calculate_cost(summary_input, summary_output, model_pricing)
    relevance_cost = calculate_cost(relevance_input, relevance_output, model_pricing)
    nl_total_cost = calculate_cost(nl_total_input, nl_total_output, model_pricing)

    # Weekly report costs (if available)
    weekly_phase1_input = 0
    weekly_phase1_output = 0
    weekly_phase2_input = 0
    weekly_phase2_output = 0
    weekly_report_count = len(weekly_analyses)

    if weekly_analyses:
        for analysis in weekly_analyses:
            for phase1_op in analysis.phase1_operations:
                weekly_phase1_input += phase1_op.input_tokens
                weekly_phase1_output += phase1_op.output_tokens

            weekly_phase2_input += analysis.phase2_operation.input_tokens
            weekly_phase2_output += analysis.phase2_operation.output_tokens

    weekly_total_input = weekly_phase1_input + weekly_phase2_input
    weekly_total_output = weekly_phase1_output + weekly_phase2_output

    weekly_phase1_cost = calculate_cost(
        weekly_phase1_input, weekly_phase1_output, model_pricing
    )
    weekly_phase2_cost = calculate_cost(
        weekly_phase2_input, weekly_phase2_output, model_pricing
    )
    weekly_total_cost = calculate_cost(
        weekly_total_input, weekly_total_output, model_pricing
    )

    # Grand totals
    grand_input = nl_total_input + weekly_total_input
    grand_output = nl_total_output + weekly_total_output
    grand_cost = calculate_cost(grand_input, grand_output, model_pricing)

    # Format report
    report = []
    report.append("=" * 65)
    report.append("LLM TOKEN COST ANALYSIS (NEWSLETTER + WEEKLY REPORTS)")
    report.append("=" * 65)
    report.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Newsletters Analyzed: {len(newsletter_analyses)}")
    report.append(f"Weekly Reports Generated: {weekly_report_count}")
    report.append(f"Model: {model_pricing.model} ({model_pricing.provider})")
    report.append(
        f"Pricing: ${model_pricing.input_cost_per_1m:.2f}/1M input, ${model_pricing.output_cost_per_1m:.2f}/1M output"
    )
    report.append("")

    # Newsletter processing section
    report.append("-" * 65)
    report.append("NEWSLETTER PROCESSING (3 calls per newsletter)")
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
    report.append(
        f"{'Relevance Scoring':<20} {relevance_input:>12,} {relevance_output:>12,} ${relevance_cost['total_cost']:>9.4f}"
    )
    report.append("-" * 65)
    report.append(
        f"{'SUBTOTAL':<20} {nl_total_input:>12,} {nl_total_output:>12,} ${nl_total_cost['total_cost']:>9.4f}"
    )
    report.append("")

    # Weekly report section
    if weekly_analyses:
        report.append("-" * 65)
        report.append(f"WEEKLY REPORT SYNTHESIS ({weekly_report_count} topic reports)")
        report.append("-" * 65)
        report.append(
            f"{'Operation':<20} {'Input Tokens':>12} {'Output Tokens':>12} {'Cost':>10}"
        )
        report.append("-" * 65)
        report.append(
            f"{'Phase 1: Extract':<20} {weekly_phase1_input:>12,} {weekly_phase1_output:>12,} ${weekly_phase1_cost['total_cost']:>9.4f}"
        )
        report.append(
            f"{'Phase 2: Synthesize':<20} {weekly_phase2_input:>12,} {weekly_phase2_output:>12,} ${weekly_phase2_cost['total_cost']:>9.4f}"
        )
        report.append("-" * 65)
        report.append(
            f"{'SUBTOTAL':<20} {weekly_total_input:>12,} {weekly_total_output:>12,} ${weekly_total_cost['total_cost']:>9.4f}"
        )
        report.append("")

    # Grand total
    report.append("-" * 65)
    report.append("GRAND TOTAL (Newsletter + Weekly)")
    report.append("-" * 65)
    report.append(
        f"{'TOTAL':<20} {grand_input:>12,} {grand_output:>12,} ${grand_cost['total_cost']:>9.4f}"
    )
    report.append("")

    # Cost breakdown
    report.append("-" * 65)
    report.append("COST BREAKDOWN")
    report.append("-" * 65)
    nl_cost_per = nl_total_cost["total_cost"] / len(newsletter_analyses)
    report.append(f"Per newsletter (processing only): ${nl_cost_per:.4f}")

    if weekly_analyses:
        weekly_cost_per_report = weekly_total_cost["total_cost"] / weekly_report_count
        report.append(f"Per weekly report: ${weekly_cost_per_report:.4f}")
        report.append(
            f"Total for {len(newsletter_analyses)} newsletters + {weekly_report_count} reports: ${grand_cost['total_cost']:.4f}"
        )
    else:
        report.append(
            f"Total for {len(newsletter_analyses)} newsletters: ${nl_total_cost['total_cost']:.4f}"
        )

    report.append("")

    # Projections
    report.append("-" * 65)
    report.append("MONTHLY PROJECTIONS")
    report.append("-" * 65)
    report.append(f"100 newsletters/month (processing only): ${nl_cost_per * 100:.2f}")
    report.append(
        f"1,000 newsletters/month (processing only): ${nl_cost_per * 1000:.2f}"
    )

    if weekly_analyses:
        # Estimate weekly reports per month (assume 4 weeks, avg topics)
        avg_reports_per_week = weekly_report_count / max(
            len(set(a.week_id for a in weekly_analyses)), 1
        )
        monthly_weekly_reports = avg_reports_per_week * 4
        monthly_weekly_cost = weekly_cost_per_report * monthly_weekly_reports

        report.append("")
        report.append(
            f"~{monthly_weekly_reports:.0f} weekly reports/month: ${monthly_weekly_cost:.2f}"
        )
        report.append(
            f"100 newsletters + weekly reports: ${nl_cost_per * 100 + monthly_weekly_cost:.2f}"
        )
        report.append(
            f"1,000 newsletters + weekly reports: ${nl_cost_per * 1000 + monthly_weekly_cost:.2f}"
        )

    report.append("=" * 65)

    return "\n".join(report)
