#!/usr/bin/env python3
"""
Generate evaluation comparison report from baseline and enhanced metrics.

Usage:
    python generate_evaluation_report.py \\
        --baseline=results/metrics_baseline_20260211_120000 \\
        --enhanced=results/metrics_enhanced_20260211_130000 \\
        --output=docs/evaluation/PHASE_0-5_RESULTS.md
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def load_metric(file_path: Path) -> Optional[float]:
    """Load a metric value from Prometheus JSON response."""
    if not file_path.exists():
        return None

    try:
        with open(file_path) as f:
            data = json.load(f)

        # Extract value from Prometheus response format
        # {"status":"success","data":{"resultType":"vector","result":[{"metric":{},"value":[timestamp,value]}]}}
        if data.get("status") == "success":
            results = data.get("data", {}).get("result", [])
            if results and len(results) > 0:
                value = results[0].get("value", [None, None])[1]
                if value is not None:
                    return float(value)
        return None
    except Exception as e:
        print(f"Warning: Failed to load {file_path}: {e}", file=sys.stderr)
        return None


def calculate_improvement(baseline: Optional[float], enhanced: Optional[float]) -> tuple[float, str]:
    """Calculate percentage improvement from baseline to enhanced."""
    if baseline is None or enhanced is None:
        return 0.0, "N/A"

    if baseline == 0:
        if enhanced == 0:
            return 0.0, "No change"
        return 100.0, f"+{enhanced:.2f} (new metric)"

    change = ((enhanced - baseline) / baseline) * 100
    sign = "+" if change > 0 else ""
    return change, f"{sign}{change:.1f}%"


def format_duration(seconds: Optional[float]) -> str:
    """Format seconds as human-readable duration."""
    if seconds is None:
        return "N/A"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def format_rate(per_second: Optional[float]) -> str:
    """Format rate as per minute."""
    if per_second is None:
        return "N/A"
    per_minute = per_second * 60
    return f"{per_minute:.2f}/min"


def format_percentage(value: Optional[float]) -> str:
    """Format value as percentage."""
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def load_all_metrics(metrics_dir: Path) -> dict[str, Optional[float]]:
    """Load all metrics from a directory."""
    return {
        "step_failures": load_metric(metrics_dir / "step_failures.json"),
        "tool_errors": load_metric(metrics_dir / "tool_errors.json"),
        "step_duration_p95": load_metric(metrics_dir / "step_duration_p95.json"),
        "session_success_rate": load_metric(metrics_dir / "session_success_rate.json"),
        "llm_calls": load_metric(metrics_dir / "llm_calls.json"),
        "mtfr": load_metric(metrics_dir / "mtfr.json"),
        # Enhanced-only metrics
        "recovery_triggers": load_metric(metrics_dir / "recovery_triggers.json"),
        "recovery_success_rate": load_metric(metrics_dir / "recovery_success_rate.json"),
        "duplicate_blocks": load_metric(metrics_dir / "duplicate_blocks.json"),
        "duplicate_suppression_rate": load_metric(metrics_dir / "duplicate_suppression_rate.json"),
        "cache_hit_rate": load_metric(metrics_dir / "cache_hit_rate.json"),
        "args_canonicalized": load_metric(metrics_dir / "args_canonicalized.json"),
        "recovery_duration_p95": load_metric(metrics_dir / "recovery_duration_p95.json"),
        "snapshot_generation": load_metric(metrics_dir / "snapshot_generation.json"),
    }


def generate_summary_table(baseline: Dict, enhanced: Dict) -> str:
    """Generate summary comparison table."""
    rows = []

    # Step Failure Rate
    b_failures = baseline.get("step_failures")
    e_failures = enhanced.get("step_failures")
    change, change_str = calculate_improvement(b_failures, e_failures)
    status = "✅" if change < -10 else "⚠️" if change < 0 else "❌"
    rows.append(
        f"| Step Failure Rate | {format_rate(b_failures)} | {format_rate(e_failures)} | {change_str} | {status} |"
    )

    # Tool Error Rate
    b_tool_err = baseline.get("tool_errors")
    e_tool_err = enhanced.get("tool_errors")
    change, change_str = calculate_improvement(b_tool_err, e_tool_err)
    status = "✅" if change < -20 else "⚠️" if change < 0 else "❌"
    rows.append(
        f"| Tool Error Rate | {format_rate(b_tool_err)} | {format_rate(e_tool_err)} | {change_str} | {status} |"
    )

    # Recovery Success Rate (enhanced only)
    e_recovery = enhanced.get("recovery_success_rate")
    status = "✅" if e_recovery and e_recovery >= 0.7 else "⚠️" if e_recovery and e_recovery >= 0.5 else "❌"
    rows.append(
        f"| Recovery Success Rate | N/A | {format_percentage(e_recovery)} | NEW | {status} |"
    )

    # Duplicate Suppression Rate (enhanced only)
    e_dup_supp = enhanced.get("duplicate_suppression_rate")
    status = "✅" if e_dup_supp and e_dup_supp >= 0.5 else "⚠️" if e_dup_supp and e_dup_supp >= 0.3 else "❌"
    rows.append(
        f"| Duplicate Suppression | N/A | {format_percentage(e_dup_supp)} | NEW | {status} |"
    )

    # Cache Hit Rate (enhanced only)
    e_cache = enhanced.get("cache_hit_rate")
    status = "✅" if e_cache and e_cache >= 0.8 else "⚠️" if e_cache and e_cache >= 0.6 else "❌"
    rows.append(
        f"| Tool Cache Hit Rate | N/A | {format_percentage(e_cache)} | NEW | {status} |"
    )

    # P95 Step Duration
    b_dur = baseline.get("step_duration_p95")
    e_dur = enhanced.get("step_duration_p95")
    change, change_str = calculate_improvement(b_dur, e_dur)
    status = "✅" if change < -10 else "⚠️" if change < 0 else "❌"
    rows.append(
        f"| P95 Step Duration | {format_duration(b_dur)} | {format_duration(e_dur)} | {change_str} | {status} |"
    )

    return "\n".join(rows)


def generate_regression_table(baseline: Dict, enhanced: Dict) -> str:
    """Generate regression metrics table."""
    rows = []

    # Session Success Rate
    b_success = baseline.get("session_success_rate")
    e_success = enhanced.get("session_success_rate")
    change, change_str = calculate_improvement(b_success, e_success)
    threshold_met = abs(change) <= 10 if b_success and e_success else False
    status = "✅ PASS" if threshold_met else "⚠️ REVIEW"
    rows.append(
        f"| Session Success Rate | {format_percentage(b_success)} | {format_percentage(e_success)} | {change_str} | {status} |"
    )

    # MTFR
    b_mtfr = baseline.get("mtfr")
    e_mtfr = enhanced.get("mtfr")
    change, change_str = calculate_improvement(b_mtfr, e_mtfr)
    threshold_met = change <= 15 if b_mtfr and e_mtfr else False
    status = "✅ PASS" if threshold_met else "⚠️ REVIEW"
    rows.append(
        f"| Mean Time to First Response | {format_duration(b_mtfr)} | {format_duration(e_mtfr)} | {change_str} | {status} |"
    )

    # LLM API Calls
    b_llm = baseline.get("llm_calls")
    e_llm = enhanced.get("llm_calls")
    change, change_str = calculate_improvement(b_llm, e_llm)
    threshold_met = change <= 15 if b_llm and e_llm else False
    status = "✅ PASS" if threshold_met else "⚠️ REVIEW"
    rows.append(
        f"| LLM API Calls | {format_rate(b_llm)} | {format_rate(e_llm)} | {change_str} | {status} |"
    )

    return "\n".join(rows)


def evaluate_success_criteria(baseline: dict, enhanced: dict) -> tuple[bool, str]:
    """Evaluate if success criteria are met."""
    failures = []

    # Primary metrics
    b_failures = baseline.get("step_failures", 0)
    e_failures = enhanced.get("step_failures", 0)
    if b_failures > 0:
        reduction = ((b_failures - e_failures) / b_failures) * 100
        if reduction < 25:
            failures.append(f"Step failure reduction: {reduction:.1f}% (target: ≥25%)")

    e_recovery = enhanced.get("recovery_success_rate")
    if e_recovery and e_recovery < 0.65:
        failures.append(f"Recovery success rate: {e_recovery*100:.1f}% (target: ≥65%)")

    e_dup_supp = enhanced.get("duplicate_suppression_rate")
    if e_dup_supp and e_dup_supp < 0.5:
        failures.append(f"Duplicate suppression: {e_dup_supp*100:.1f}% (target: ≥50%)")

    e_cache = enhanced.get("cache_hit_rate")
    if e_cache and e_cache < 0.75:
        failures.append(f"Cache hit rate: {e_cache*100:.1f}% (target: ≥75%)")

    # Regression metrics
    b_success = baseline.get("session_success_rate")
    e_success = enhanced.get("session_success_rate")
    if b_success and e_success:
        change = abs(((e_success - b_success) / b_success) * 100)
        if change > 10:
            failures.append(f"Session success rate change: {change:.1f}% (threshold: ±10%)")

    b_mtfr = baseline.get("mtfr")
    e_mtfr = enhanced.get("mtfr")
    if b_mtfr and e_mtfr:
        increase = ((e_mtfr - b_mtfr) / b_mtfr) * 100
        if increase > 15:
            failures.append(f"MTFR increase: {increase:.1f}% (threshold: ≤15%)")

    if failures:
        return False, "\n".join(f"  - ❌ {f}" for f in failures)
    return True, "✅ All success criteria met!"


def generate_report(baseline_dir: Path, enhanced_dir: Path, output_file: Path) -> None:
    """Generate evaluation comparison report."""

    # Load metrics
    print(f"Loading baseline metrics from {baseline_dir}...")
    baseline = load_all_metrics(baseline_dir)

    print(f"Loading enhanced metrics from {enhanced_dir}...")
    enhanced = load_all_metrics(enhanced_dir)

    # Evaluate success criteria
    success, criteria_status = evaluate_success_criteria(baseline, enhanced)

    # Generate report
    report = f"""# Phase 0-5 Enhancement Evaluation Results

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Baseline Directory**: `{baseline_dir}`
**Enhanced Directory**: `{enhanced_dir}`

---

## Executive Summary

{criteria_status}

---

## Primary Metrics Comparison

| Metric | Baseline | Enhanced | Change | Status |
|--------|----------|----------|--------|--------|
{generate_summary_table(baseline, enhanced)}

---

## Regression Analysis

| Metric | Baseline | Enhanced | Change | Status |
|--------|----------|----------|--------|--------|
{generate_regression_table(baseline, enhanced)}

---

## Detailed Enhancement Metrics

### Response Recovery
- **Recovery Trigger Rate**: {format_rate(enhanced.get('recovery_triggers'))}
- **Recovery Success Rate**: {format_percentage(enhanced.get('recovery_success_rate'))}
- **P95 Recovery Duration**: {format_duration(enhanced.get('recovery_duration_p95'))}

### Duplicate Suppression
- **Duplicate Blocks**: {format_rate(enhanced.get('duplicate_blocks'))}
- **Suppression Effectiveness**: {format_percentage(enhanced.get('duplicate_suppression_rate'))}

### Argument Canonicalization
- **Arguments Canonicalized**: {format_rate(enhanced.get('args_canonicalized'))}

### Tool Definition Caching
- **Cache Hit Rate**: {format_percentage(enhanced.get('cache_hit_rate'))}

### Failure Snapshots
- **Snapshot Generation Rate**: {format_rate(enhanced.get('snapshot_generation'))}

---

## Conclusion

{"✅ **EVALUATION PASSED** - All success criteria met. Ready for production deployment." if success else "⚠️ **EVALUATION NEEDS REVIEW** - Some success criteria not met. Review findings before deployment."}

### Key Wins
"""

    # Add key wins based on actual improvements
    b_failures = baseline.get("step_failures")
    e_failures = enhanced.get("step_failures")
    if b_failures and e_failures and e_failures < b_failures:
        reduction = ((b_failures - e_failures) / b_failures) * 100
        report += f"1. {reduction:.0f}% reduction in step failures\n"

    b_tool_err = baseline.get("tool_errors")
    e_tool_err = enhanced.get("tool_errors")
    if b_tool_err and e_tool_err and e_tool_err < b_tool_err:
        reduction = ((b_tool_err - e_tool_err) / b_tool_err) * 100
        report += f"2. {reduction:.0f}% reduction in tool errors\n"

    e_recovery = enhanced.get("recovery_success_rate")
    if e_recovery and e_recovery >= 0.65:
        report += f"3. {e_recovery*100:.0f}% recovery success rate achieved\n"

    e_cache = enhanced.get("cache_hit_rate")
    if e_cache and e_cache >= 0.75:
        report += f"4. {e_cache*100:.0f}% tool cache hit rate\n"

    report += """
### Recommended Next Steps
1. Review Grafana dashboards for detailed trends
2. Monitor alert rules for 48 hours in staging
3. Create gradual rollout plan (10% → 50% → 100%)
4. Collect production metrics for Phase 7 optimization

---

*Report generated by `scripts/generate_evaluation_report.py`*
"""

    # Write report
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report)
    print(f"\n✅ Report generated successfully: {output_file}")

    if not success:
        print("\n⚠️  Warning: Some success criteria were not met. Review the report.")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate evaluation comparison report from baseline and enhanced metrics"
    )
    parser.add_argument(
        "--baseline",
        required=True,
        type=Path,
        help="Path to baseline metrics directory (e.g., results/metrics_baseline_20260211_120000)",
    )
    parser.add_argument(
        "--enhanced",
        required=True,
        type=Path,
        help="Path to enhanced metrics directory (e.g., results/metrics_enhanced_20260211_130000)",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output markdown file (e.g., docs/evaluation/PHASE_0-5_RESULTS.md)",
    )

    args = parser.parse_args()

    # Validate input directories
    if not args.baseline.exists():
        print(f"Error: Baseline directory not found: {args.baseline}", file=sys.stderr)
        sys.exit(1)

    if not args.enhanced.exists():
        print(f"Error: Enhanced directory not found: {args.enhanced}", file=sys.stderr)
        sys.exit(1)

    # Generate report
    generate_report(args.baseline, args.enhanced, args.output)


if __name__ == "__main__":
    main()
