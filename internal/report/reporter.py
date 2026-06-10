"""
Rich Terminal Reporter

Renders beautiful, colored cost estimation reports in the terminal.
Also supports JSON and HTML output formats.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from internal.pricing.aws_pricing import CostEstimate
from internal.compare.comparator import CostComparison, ResourceDiff
from internal.budget.budget_checker import BudgetResult


def _make_console(**kwargs) -> Console:
    """Create a Console that safely handles Windows CP1252 terminals."""
    # Force UTF-8 output on Windows to avoid UnicodeEncodeError with emoji
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, io.UnsupportedOperation):
            pass
    return Console(**kwargs)


console = _make_console()


# ─── Confidence Color Mapping ─────────────────────────────────────────────────

CONFIDENCE_COLORS = {
    "high":    "green",
    "medium":  "yellow",
    "low":     "orange3",
    "unknown": "red",
}

ACTION_COLORS = {
    "create":  "bold green",
    "delete":  "bold red",
    "update":  "bold yellow",
    "replace": "bold magenta",
    "no-op":   "dim",
}

ACTION_SYMBOLS = {
    "create":  "✚",
    "delete":  "✖",
    "update":  "~",
    "replace": "↺",
    "no-op":   "·",
}


class Reporter:
    """
    Renders cost report output in multiple formats.

    Usage:
        reporter = Reporter()
        reporter.print_cost_table(estimates, plan_path="plan.json")
        reporter.print_comparison(comparison)
        reporter.print_budget_result(budget_result, total_cost)
    """

    def __init__(self, no_color: bool = False):
        self._console = _make_console(no_color=no_color, highlight=False)

    def print_header(self, plan_path: str) -> None:
        """Print the tool header banner."""
        self._console.print()
        self._console.print(
            Panel.fit(
                "[bold cyan]** Terraform Cost Predictor **[/bold cyan]\n"
                f"[dim]Analyzing plan: [italic]{plan_path}[/italic][/dim]",
                border_style="cyan",
                padding=(0, 2),
            )
        )
        self._console.print()

    def print_cost_table(
        self,
        estimates: list[dict[str, Any]],
        plan_path: str = "",
        show_breakdown: bool = False,
    ) -> None:
        """Print the main cost estimation table."""
        if plan_path:
            self.print_header(plan_path)

        table = Table(
            title="[bold]Estimated Monthly Costs[/bold]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold white on dark_blue",
            border_style="blue",
            row_styles=["", "dim"],
            expand=True,
            min_width=80,
        )

        table.add_column("Action", style="bold", justify="center", width=8)
        table.add_column("Resource", no_wrap=False, min_width=30)
        table.add_column("Type", style="cyan", min_width=20)
        table.add_column("Confidence", justify="center", width=12)
        table.add_column("Monthly Cost", justify="right", style="bold", width=14)

        total_cost = 0.0
        unsupported_count = 0

        for entry in estimates:
            action = entry.get("action", "create")
            address = entry.get("address", "")
            resource_type = entry.get("resource_type", "")
            monthly_cost = entry.get("monthly_cost", 0.0)
            confidence = entry.get("confidence", "unknown")
            is_supported = entry.get("is_supported", True)

            # Style action symbol
            action_color = ACTION_COLORS.get(action, "white")
            action_sym = ACTION_SYMBOLS.get(action, "?")
            action_cell = Text(f"{action_sym} {action}", style=action_color)

            # Style cost
            if action == "delete":
                cost_cell = Text(f"-${monthly_cost:,.2f}", style="bold red")
                total_cost -= monthly_cost
            elif not is_supported:
                cost_cell = Text("—", style="dim")
                unsupported_count += 1
            else:
                cost_cell = Text(f"${monthly_cost:,.2f}", style="bold green")
                total_cost += monthly_cost

            # Confidence badge
            conf_color = CONFIDENCE_COLORS.get(confidence, "white")
            conf_cell = Text(f"[{confidence}]", style=conf_color)

            table.add_row(action_cell, address, resource_type, conf_cell, cost_cell)

        self._console.print(table)

        # Summary footer
        self._print_summary(total_cost, len(estimates), unsupported_count)

    def _print_summary(
        self, total: float, total_resources: int, unsupported: int
    ) -> None:
        """Print the summary panel."""
        supported = total_resources - unsupported
        summary_text = (
            f"[bold]Total Resources:[/bold]    {total_resources}\n"
            f"[bold]Priced Resources:[/bold]   {supported}\n"
            f"[bold]Unsupported:[/bold]        [dim]{unsupported}[/dim]"
        )
        cost_text = (
            f"[bold white]Estimated Monthly Cost[/bold white]\n\n"
            f"[bold bright_green]${total:,.2f}[/bold bright_green] [dim]USD / month[/dim]\n\n"
            f"[dim]≈ ${total * 12:,.2f} / year[/dim]"
        )

        self._console.print()
        self._console.print(
            Columns(
                [
                    Panel(summary_text, title="[bold]Summary[/bold]", border_style="blue", expand=True),
                    Panel(cost_text, title="[bold]Total Cost[/bold]", border_style="bright_green", expand=True),
                ],
                equal=True,
            )
        )
        self._console.print()

    def print_comparison(self, comparison: CostComparison) -> None:
        """Print the cost diff comparison — the 'killer feature'."""
        self._console.print(Rule("[bold cyan]Cost Comparison[/bold cyan]", style="cyan"))
        self._console.print()

        # High-level summary
        delta_str = f"+${comparison.delta:,.2f}" if comparison.delta >= 0 else f"-${abs(comparison.delta):,.2f}"
        delta_pct_str = f"+{comparison.delta_percent:.1f}%" if comparison.delta_percent >= 0 else f"{comparison.delta_percent:.1f}%"
        delta_color = "red" if comparison.delta > 0 else "green"

        self._console.print(
            Panel(
                f"[dim]Previous Run:[/dim]   [bold]${comparison.previous_total:,.2f}[/bold]  "
                f"[dim]({comparison.previous_timestamp[:10]})[/dim]\n"
                f"[dim]Current Cost:[/dim]   [bold]${comparison.current_total:,.2f}[/bold]\n"
                f"[dim]Delta:         [/dim]   [{delta_color}][bold]{delta_str}[/bold] ({delta_pct_str})[/{delta_color}]",
                title="[bold]Cost Delta[/bold]",
                border_style=delta_color,
                padding=(0, 2),
            )
        )
        self._console.print()

        # Killer Feature: Top cost drivers
        if comparison.top_drivers:
            self._console.print("[bold]>> Cost changed because:[/bold]")
            for driver in comparison.top_drivers:
                sym, color = self._driver_style(driver)
                delta_str = f"+${driver.delta:,.2f}" if driver.delta >= 0 else f"-${abs(driver.delta):,.2f}"
                self._console.print(
                    f"  [{color}]{sym}[/{color}] [cyan]{driver.address}[/cyan]  "
                    f"[{color}][bold]{delta_str}/mo[/bold][/{color}]"
                )
                reason_lines = driver.reason.split("\n")
                for line in reason_lines[1:]:
                    self._console.print(f"      [dim]{line.strip()}[/dim]")
            self._console.print()

        # Resource diff table
        diff_table = Table(
            title="[bold]Resource Changes[/bold]",
            box=box.SIMPLE_HEAVY,
            border_style="dim",
            show_header=True,
            header_style="bold",
            expand=True,
        )
        diff_table.add_column("Status", width=10, justify="center")
        diff_table.add_column("Resource", min_width=30)
        diff_table.add_column("Previous", justify="right", width=12)
        diff_table.add_column("Current", justify="right", width=12)
        diff_table.add_column("Delta", justify="right", width=14)

        all_diffs = (
            comparison.added + comparison.removed +
            comparison.changed + comparison.unchanged
        )
        for diff in all_diffs:
            sym, color = self._driver_style(diff)
            status_cell = Text(f"{sym} {diff.status}", style=color)
            delta_sign = "+" if diff.delta >= 0 else ""
            delta_cell = Text(
                f"{delta_sign}${diff.delta:,.2f}" if diff.delta != 0 else "—",
                style=color if diff.delta != 0 else "dim",
            )
            diff_table.add_row(
                status_cell,
                diff.address,
                f"${diff.previous_cost:,.2f}" if diff.previous_cost else "—",
                f"${diff.current_cost:,.2f}" if diff.current_cost else "—",
                delta_cell,
            )

        self._console.print(diff_table)

    def print_budget_result(
        self, result: BudgetResult, estimated_cost: float, budget_limit: float | None = None
    ) -> None:
        """Print budget check result with visual progress bar."""
        self._console.print(Rule("[bold]Budget Policy Check[/bold]", style="blue"))
        self._console.print()

        if result.passed and not result.violations and not result.warnings:
            if budget_limit:
                usage = (estimated_cost / budget_limit) * 100
                bar_color = "green" if usage < 80 else "yellow"
                self._console.print(
                    f"  [green]✓ PASSED[/green] — Estimated [bold]${estimated_cost:,.2f}[/bold] "
                    f"of [bold]${budget_limit:,.2f}[/bold] monthly budget "
                    f"([{bar_color}]{usage:.1f}%[/{bar_color}])"
                )
            else:
                self._console.print(f"  [green]✓ No budget policy configured.[/green]")

        for warning in result.warnings:
            self._console.print(
                Panel(
                    f"[yellow]⚠  BUDGET WARNING[/yellow]\n\n"
                    f"Estimated: [bold]${warning.estimated_cost:,.2f}[/bold] / "
                    f"Limit: [bold]${warning.limit:,.2f}[/bold]\n"
                    f"Usage: [yellow]{warning.usage_percent:.1f}%[/yellow] "
                    f"(alert at {warning.threshold_percent:.0f}%)",
                    border_style="yellow",
                )
            )

        for violation in result.violations:
            self._console.print(
                Panel(
                    f"[red bold]✖  BUDGET EXCEEDED — PIPELINE BLOCKED[/red bold]\n\n"
                    f"Estimated cost:  [bold red]${violation.estimated_cost:,.2f}[/bold red]\n"
                    f"Budget limit:    [bold]${violation.limit:,.2f}[/bold]\n"
                    f"Overage:         [bold red]+${violation.overage:,.2f}[/bold red] "
                    f"(+{violation.overage_percent:.1f}%)\n\n"
                    f"[dim]Fix: Reduce resources or raise the budget in budget.yaml[/dim]",
                    title=f"[bold red]Budget Policy: {violation.environment}[/bold red]",
                    border_style="red",
                )
            )
        self._console.print()

    def print_history_table(self, runs: list[dict[str, Any]]) -> None:
        """Print the cost history table."""
        if not runs:
            self._console.print("[dim]No history found. Run with [bold]--save[/bold] to record runs.[/dim]")
            return

        table = Table(
            title="[bold]Cost History[/bold]",
            box=box.ROUNDED,
            border_style="blue",
            header_style="bold white on dark_blue",
        )
        table.add_column("Run ID", style="dim", width=14)
        table.add_column("Date", width=12)
        table.add_column("Label", style="cyan")
        table.add_column("Resources", justify="right", width=10)
        table.add_column("Monthly Cost", justify="right", style="bold green", width=14)

        for run in runs:
            ts = run.get("timestamp", "")[:10]
            run_id_short = run.get("run_id", "")[:8]
            table.add_row(
                run_id_short,
                ts,
                run.get("label") or "[dim]—[/dim]",
                str(run.get("resource_count", 0)),
                f"${run.get('total_cost', 0.0):,.2f}",
            )

        self._console.print(table)

    # ─── JSON / HTML Export ───────────────────────────────────────────────────

    def to_json(
        self,
        estimates: list[dict[str, Any]],
        total_cost: float,
        comparison: CostComparison | None = None,
        budget_result: BudgetResult | None = None,
    ) -> str:
        """Serialize the full report to JSON."""
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_monthly_cost": round(total_cost, 2),
            "currency": "USD",
            "resources": estimates,
        }
        if comparison:
            output["comparison"] = {
                "previous_total": comparison.previous_total,
                "current_total": comparison.current_total,
                "delta": comparison.delta,
                "delta_percent": comparison.delta_percent,
                "top_drivers": [
                    {
                        "address": d.address,
                        "status": d.status,
                        "delta": d.delta,
                        "reason": d.reason,
                    }
                    for d in comparison.top_drivers
                ],
            }
        if budget_result:
            output["budget"] = {
                "passed": budget_result.passed,
                "message": budget_result.message,
                "violations": len(budget_result.violations),
                "warnings": len(budget_result.warnings),
            }
        return json.dumps(output, indent=2, default=str)

    def to_html(
        self,
        estimates: list[dict[str, Any]],
        total_cost: float,
        plan_path: str = "",
    ) -> str:
        """Generate a standalone HTML report."""
        rows = ""
        for e in estimates:
            action = e.get("action", "create")
            cost = e.get("monthly_cost", 0.0)
            color_cls = {
                "create": "create", "delete": "delete",
                "update": "update", "replace": "replace",
            }.get(action, "")
            cost_str = f"${cost:,.2f}" if e.get("is_supported") else "—"
            rows += (
                f"<tr class='{color_cls}'>"
                f"<td>{ACTION_SYMBOLS.get(action,'?')} {action}</td>"
                f"<td>{e.get('address','')}</td>"
                f"<td>{e.get('resource_type','')}</td>"
                f"<td class='conf-{e.get('confidence','unknown')}'>{e.get('confidence','')}</td>"
                f"<td class='cost'>{cost_str}</td>"
                f"</tr>\n"
            )
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return HTML_TEMPLATE.format(
            plan_path=plan_path,
            timestamp=ts,
            total=f"${total_cost:,.2f}",
            rows=rows,
        )

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _driver_style(self, diff: ResourceDiff) -> tuple[str, str]:
        status_map = {
            "added":     ("✚", "green"),
            "removed":   ("✖", "red"),
            "changed":   ("~", "yellow"),
            "replaced":  ("↺", "magenta"),
            "unchanged": ("·", "dim"),
        }
        return status_map.get(diff.status, ("?", "white"))


# ─── HTML Template ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Terraform Cost Report</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #e6edf3; padding: 2rem; }}
    h1 {{ color: #58a6ff; margin-bottom: 0.25rem; font-size: 1.8rem; }}
    .meta {{ color: #8b949e; margin-bottom: 2rem; font-size: 0.9rem; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; }}
    th {{ background: #161b22; color: #58a6ff; padding: 0.75rem 1rem; text-align: left; border-bottom: 2px solid #30363d; }}
    td {{ padding: 0.65rem 1rem; border-bottom: 1px solid #21262d; }}
    tr:hover td {{ background: #161b22; }}
    .create td:first-child {{ color: #3fb950; }}
    .delete td:first-child {{ color: #f85149; }}
    .update td:first-child {{ color: #d29922; }}
    .replace td:first-child {{ color: #bc8cff; }}
    .cost {{ font-weight: bold; text-align: right; }}
    .conf-high {{ color: #3fb950; }}
    .conf-medium {{ color: #d29922; }}
    .conf-low {{ color: #e3b341; }}
    .conf-unknown {{ color: #f85149; }}
    .total {{ font-size: 1.5rem; font-weight: bold; color: #3fb950; padding: 1rem; background: #161b22; border-radius: 8px; display: inline-block; }}
    .total span {{ color: #8b949e; font-size: 0.9rem; font-weight: normal; }}
  </style>
</head>
<body>
  <h1>🔮 Terraform Cost Report</h1>
  <p class="meta">Plan: <code>{plan_path}</code> &nbsp;|&nbsp; Generated: {timestamp}</p>
  <table>
    <thead>
      <tr><th>Action</th><th>Resource</th><th>Type</th><th>Confidence</th><th>Monthly Cost</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <div class="total">Estimated Monthly Cost: {total} <span>USD</span></div>
</body>
</html>
"""
