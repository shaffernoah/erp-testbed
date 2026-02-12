"""Scenario execution framework.

Runs predefined scenarios against the testbed database,
captures agent traces, and reports results.
"""

import json
import time
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from database.connection import get_session
from analysis.llm_client import LLMClient
from agents.tool_registry import ToolRegistry
from agents.agent_runner import AgentRunner

console = Console()


@dataclass
class Scenario:
    """Definition of a test scenario."""
    id: str
    name: str
    description: str
    persona: str  # "vendor_ops", "vendor_sales", "restaurant"
    user_message: str
    expected_tools: list[str] = field(default_factory=list)
    expected_output_keys: list[str] = field(default_factory=list)


@dataclass
class ScenarioResult:
    """Result of running a scenario."""
    scenario: Scenario
    success: bool
    final_answer: str
    tool_calls: list
    elapsed_seconds: float
    error: str | None = None


def run_scenario(
    scenario: Scenario,
    system_prompt: str,
    tool_registry: ToolRegistry,
    llm_client: LLMClient,
) -> ScenarioResult:
    """Execute a single scenario and return the result."""
    console.print(Panel(
        f"[bold]{scenario.name}[/bold]\n{scenario.description}",
        title=f"Scenario {scenario.id}",
        border_style="blue",
    ))
    console.print(f"[dim]User message:[/dim] {scenario.user_message}\n")

    runner = AgentRunner(
        llm_client=llm_client,
        tool_registry=tool_registry,
        system_prompt=system_prompt,
    )

    start = time.time()
    try:
        result = runner.run(scenario.user_message)
        elapsed = time.time() - start

        console.print(f"\n[green]Completed in {elapsed:.1f}s[/green]")
        console.print(f"Tool calls: {result.tool_calls_count}")
        console.print(Panel(result.final_answer[:2000], title="Agent Response"))

        return ScenarioResult(
            scenario=scenario,
            success=True,
            final_answer=result.final_answer,
            tool_calls=result.trace,
            elapsed_seconds=elapsed,
        )
    except Exception as e:
        elapsed = time.time() - start
        console.print(f"\n[red]Error: {e}[/red]")
        return ScenarioResult(
            scenario=scenario,
            success=False,
            final_answer="",
            tool_calls=[],
            elapsed_seconds=elapsed,
            error=str(e),
        )


def run_all_scenarios(scenarios: list[Scenario], system_prompt: str,
                      tool_registry: ToolRegistry, llm_client: LLMClient):
    """Run all scenarios and print a summary."""
    results = []
    for scenario in scenarios:
        result = run_scenario(scenario, system_prompt, tool_registry, llm_client)
        results.append(result)
        console.print()

    # Summary
    passed = sum(1 for r in results if r.success)
    console.print(f"\n[bold]Results: {passed}/{len(results)} scenarios passed[/bold]")
    for r in results:
        status = "[green]PASS[/green]" if r.success else f"[red]FAIL: {r.error}[/red]"
        console.print(f"  {r.scenario.id}: {r.scenario.name} — {status} ({r.elapsed_seconds:.1f}s)")

    return results
