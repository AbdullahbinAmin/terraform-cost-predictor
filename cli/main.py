"""
Terraform Cost Predictor — CLI Entry Point

Commands:
  cost-predict predict  [plan.json] [options]
  cost-predict history
  cost-predict history clear
  cost-predict version
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="cost-predict",
    help=(
        "🔮 Terraform Cost Predictor — Estimate AWS costs from Terraform plans before deployment."
    ),
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)

history_app = typer.Typer(help="Manage cost prediction history.")
app.add_typer(history_app, name="history")

console = Console()

__version__ = "1.1.0"


# ─── predict command ──────────────────────────────────────────────────────────


@app.command(name="predict")
def predict(
    plan_file: Path = typer.Argument(
        ...,
        help="Path to the Terraform plan JSON file (terraform show -json tfplan > plan.json)",
        exists=True,
        readable=True,
        resolve_path=True,
    ),
    budget: Optional[Path] = typer.Option(
        None,
        "--budget",
        "-b",
        help="Path to budget.yaml config for cost limit enforcement.",
        exists=True,
        readable=True,
        resolve_path=True,
    ),
    environment: str = typer.Option(
        "default",
        "--env",
        "-e",
        help="Environment name for budget policy lookup (e.g., production, staging).",
    ),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="Output format: table | json | html | infracost-json",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output-file",
        "-f",
        help="Save output to a file (auto-detected format from extension).",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        "-s",
        help="Save this run to history for future comparisons.",
    ),
    compare: bool = typer.Option(
        False,
        "--compare",
        "-c",
        help="Compare with the most recent saved run.",
    ),
    label: str = typer.Option(
        "",
        "--label",
        "-l",
        help="Label for this run (used for grouping history, e.g., 'staging').",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output (for CI environments).",
    ),
    show_breakdown: bool = typer.Option(
        False,
        "--breakdown",
        help="Show detailed cost breakdown per resource.",
    ),
    show_all: bool = typer.Option(
        False,
        "--all",
        help="Include unchanged (no-op) resources in the output.",
    ),
    refresh_pricing: bool = typer.Option(
        False,
        "--refresh-pricing",
        help="Fetch live pricing via Cloud APIs (AWS). Azure/GCP try live by default.",
    ),
) -> None:
    """
    [bold cyan]Estimate monthly AWS costs from a Terraform plan JSON file.[/bold cyan]

    [dim]Generate the plan JSON first:[/dim]
      [green]terraform plan -out=tfplan[/green]
      [green]terraform show -json tfplan > plan.json[/green]
      [green]cost-predict predict plan.json[/green]
    """
    # Lazy imports to keep startup fast
    from internal.parser.plan_parser import PlanParser
    from internal.pricing.router import PricingRouter
    from internal.budget.budget_checker import BudgetChecker
    from internal.report.reporter import Reporter
    from internal.compare.comparator import CostComparator
    from storage.history import HistoryStore

    reporter = Reporter(no_color=no_color)

    # 1. Parse the plan
    try:
        parser = PlanParser()
        plan = parser.parse_file(plan_file)
    except Exception as e:
        console.print(f"[red]✖ Error parsing plan:[/red] {e}")
        raise typer.Exit(code=1)

    console.print(
        f"[dim]Terraform v{plan.terraform_version} | "
        f"{len(plan.resource_changes)} resource(s) in plan[/dim]"
    )

    # 2. Estimate costs
    engine = PricingRouter()
    if refresh_pricing:
        engine.aws_engine.enable_live_pricing()
    estimates = []

    resources_to_show = plan.resource_changes if show_all else plan.relevant_changes

    for resource in resources_to_show:
        config = resource.after if resource.action != "delete" else resource.before

        if resource.is_supported and resource.action != "no-op":
            cost_estimate = engine.estimate(resource.resource_type, config, resource.address)
        else:
            from internal.pricing.aws_pricing import CostEstimate

            cost_estimate = CostEstimate(
                resource_address=resource.address,
                resource_type=resource.resource_type,
                monthly_cost=0.0,
                confidence="unknown" if not resource.is_supported else "high",
                notes=[
                    "No-op — no cost change"
                    if resource.action == "no-op"
                    else "Unsupported resource type"
                ],
                is_estimated=resource.is_supported,
            )

        entry = {
            "address": resource.address,
            "resource_type": resource.resource_type,
            "action": resource.action,
            "monthly_cost": cost_estimate.monthly_cost
            if resource.action != "delete"
            else cost_estimate.monthly_cost,
            "confidence": cost_estimate.confidence,
            "is_supported": resource.is_supported,
            "breakdown": cost_estimate.breakdown,
            "notes": cost_estimate.notes,
            "config": config,
        }
        estimates.append(entry)

    # Total cost = sum of created/updated resources (delete = savings)
    total_cost = sum(
        e["monthly_cost"]
        for e in estimates
        if e["action"] not in ("delete", "no-op") and e["is_supported"]
    )

    if output == "json":
        json_out = reporter.to_json(estimates, total_cost)
        if output_file:
            output_file.write_text(json_out, encoding="utf-8")
            console.print(f"[green]✓ JSON report saved to {output_file}[/green]")
        else:
            print(json_out)
        return

    elif output == "infracost-json":
        json_out = reporter.to_infracost_json(estimates, total_cost)
        if output_file:
            output_file.write_text(json_out, encoding="utf-8")
            console.print(
                f"[green]✓ Infracost-compatible JSON report saved to {output_file}[/green]"
            )
        else:
            print(json_out)
        return

    elif output == "html":
        html_out = reporter.to_html(estimates, total_cost, str(plan_file))
        out_path = output_file or Path("terraform-cost-report.html")
        out_path.write_text(html_out, encoding="utf-8")
        console.print(f"[green]✓ HTML report saved to {out_path}[/green]")
        return

    else:
        # Table output (default)
        reporter.print_cost_table(
            estimates,
            plan_path=str(plan_file),
            show_breakdown=show_breakdown,
        )

    # 4. Comparison
    comparison_obj = None
    if compare:
        store = HistoryStore()
        prev_run = store.get_latest_run(label=label)
        if prev_run is None:
            console.print(
                "[yellow]⚠ No previous run found for comparison. "
                "Use --save on your first run.[/yellow]"
            )
        else:
            comparator = CostComparator()
            comparison_obj = comparator.compare(estimates, prev_run)
            reporter.print_comparison(comparison_obj)

    # 5. Budget check
    budget_result = None
    if budget:
        checker = BudgetChecker(budget)
        budget_result = checker.check(total_cost, environment=environment)
        reporter.print_budget_result(budget_result, total_cost, checker.monthly_limit)

        if not budget_result.passed:
            # Save run even on failure so history is preserved
            if save:
                _save_run(estimates, total_cost, label, str(plan_file))
            raise typer.Exit(code=1)

    # 6. Save run to history
    if save:
        run_id = _save_run(estimates, total_cost, label, str(plan_file))
        console.print(f"[green]✓ Run saved to history[/green] [dim](id: {run_id[:8]})[/dim]")

    console.print()


def _save_run(
    estimates: list[dict],
    total_cost: float,
    label: str,
    plan_path: str,
) -> str:
    from storage.history import HistoryStore

    store = HistoryStore()
    resources = [
        {
            "address": e["address"],
            "resource_type": e["resource_type"],
            "monthly_cost": e["monthly_cost"],
            "config": e.get("config", {}),
        }
        for e in estimates
    ]
    return store.save_run(
        label=label,
        total_cost=total_cost,
        resources=resources,
        plan_path=plan_path,
    )


# ─── history commands ─────────────────────────────────────────────────────────


@history_app.command(name="list")
def history_list(
    label: str = typer.Option("", "--label", "-l", help="Filter by label."),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of runs to show."),
) -> None:
    """[bold cyan]List past cost prediction runs.[/bold cyan]"""
    from storage.history import HistoryStore
    from internal.report.reporter import Reporter

    store = HistoryStore()
    runs = store.list_runs(label=label, limit=limit)
    Reporter().print_history_table(runs)


@history_app.command(name="clear")
def history_clear(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """[bold red]Clear all cost prediction history.[/bold red]"""
    from storage.history import HistoryStore

    if not confirm:
        typer.confirm("Are you sure you want to delete all history?", abort=True)
    store = HistoryStore()
    deleted = store.clear_all()
    console.print(f"[green]✓ Deleted {deleted} run(s) from history.[/green]")


# ─── version command ──────────────────────────────────────────────────────────


@app.command(name="version")
def version_cmd() -> None:
    """[bold]Show the version and exit.[/bold]"""
    console.print(f"[bold cyan]Terraform Cost Predictor[/bold cyan] v{__version__}")


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
