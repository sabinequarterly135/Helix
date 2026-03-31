"""helix setup — interactive first-run configuration."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from helix_cli.config_home import get_config_home, get_global_env_path

console = Console()

PROVIDERS = {
    "gemini": {
        "label": "Gemini (Google)",
        "env_key": "GENE_GEMINI_API_KEY",
        "default_model": "gemini-2.5-flash",
    },
    "openai": {
        "label": "OpenAI",
        "env_key": "GENE_OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
    },
    "openrouter": {
        "label": "OpenRouter (multi-provider)",
        "env_key": "GENE_OPENROUTER_API_KEY",
        "default_model": "openai/gpt-4o-mini",
    },
}


def _upsert_env_line(lines: list[str], key: str, value: str) -> None:
    """Update an existing env line or append a new one."""
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            return
    lines.append(f"{key}={value}")


def setup_command(
    directory: Path | None = typer.Option(
        None,
        "--dir",
        "-d",
        help="Directory to save .env (defaults to global config: ~/.config/helix/)",
    ),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Interactive setup for API key and default provider."""
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "providers": list(PROVIDERS.keys()),
                    "config_home": str(get_config_home()),
                }
            )
        )
        return

    config_home = get_config_home()
    console.print(
        Panel(
            "[bold]Helix Setup[/bold]\n\n"
            "Configure your LLM provider and API key.\n"
            f"Config saved to: [bold]{config_home}[/bold]",
            border_style="cyan",
        )
    )

    # Provider selection
    console.print("\n[bold]Available providers:[/bold]")
    for i, (key, info) in enumerate(PROVIDERS.items(), 1):
        console.print(f"  {i}. {info['label']} [dim]({key})[/dim]")

    choice = Prompt.ask(
        "\nSelect provider",
        choices=["1", "2", "3", "gemini", "openai", "openrouter"],
        default="1",
    )

    # Map numeric choice to provider key
    provider_map = {"1": "gemini", "2": "openai", "3": "openrouter"}
    provider = provider_map.get(choice, choice)
    provider_info = PROVIDERS[provider]

    # API key
    api_key = Prompt.ask(f"\n{provider_info['label']} API key")
    if not api_key.strip():
        console.print("[red]API key cannot be empty.[/red]")
        raise typer.Exit(1)

    # Model
    default_model = provider_info["default_model"]
    model = Prompt.ask("Default model", default=default_model)

    # Write .env — to global config home by default, or explicit --dir
    if directory is not None:
        env_path = directory.resolve() / ".env"
    else:
        env_path = get_global_env_path()

    env_lines: list[str] = []
    if env_path.exists():
        env_lines = env_path.read_text(encoding="utf-8").splitlines()

    # Persist API key
    _upsert_env_line(env_lines, provider_info["env_key"], api_key.strip())

    # Persist provider and model so GeneConfig picks them up
    _upsert_env_line(env_lines, "GENE_META_PROVIDER", provider)
    _upsert_env_line(env_lines, "GENE_TARGET_PROVIDER", provider)
    _upsert_env_line(env_lines, "GENE_JUDGE_PROVIDER", provider)
    _upsert_env_line(env_lines, "GENE_META_MODEL", model)
    _upsert_env_line(env_lines, "GENE_TARGET_MODEL", model)
    _upsert_env_line(env_lines, "GENE_JUDGE_MODEL", model)

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    console.print(
        Panel(
            f"[green]Setup complete![/green]\n\n"
            f"  Provider: [bold]{provider}[/bold]\n"
            f"  Model:    [bold]{model}[/bold]\n"
            f"  Key:      [bold]{provider_info['env_key']}[/bold]\n"
            f"  Saved to: [bold]{env_path}[/bold]\n\n"
            f"[dim]Tip: Run [bold]helix init my-prompt[/bold] to create your first prompt.\n"
            f"     Override per-project with a local .env in your workspace.[/dim]",
            border_style="green",
        )
    )
