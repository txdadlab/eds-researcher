"""CLI entry point for EDS Researcher."""

from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("data/eds-researcher.log", mode="a"),
        ],
    )


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.option("--config", "-c", default="config.yaml", help="Path to config file")
@click.pass_context
def cli(ctx, verbose, config):
    """EDS Researcher — Agentic treatment discovery for Ehlers-Danlos Syndrome."""
    Path("data").mkdir(exist_ok=True)
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose


@cli.command()
@click.pass_context
def run(ctx):
    """Execute the full research pipeline (PLAN → SEARCH → ANALYZE → LEARN)."""
    from eds_researcher.scheduler.pipeline import Pipeline

    config = ctx.obj["config"]
    click.echo("Starting EDS Researcher pipeline...")

    pipeline = Pipeline(config_path=config)
    try:
        stats = pipeline.run()
        click.echo(f"\nPipeline complete:")
        click.echo(f"  Queries executed: {stats['queries']}")
        click.echo(f"  Findings collected: {stats['findings']}")
        click.echo(f"  Treatments processed: {stats['treatments']}")
        click.echo(f"  Evidence records added: {stats['evidence']}")

        # Auto-generate reports
        click.echo("\nGenerating reports...")
        full_path, delta_path = pipeline.generate_reports()
        click.echo(f"  Full report: {full_path}")
        click.echo(f"  Delta report: {delta_path}")
    finally:
        pipeline.close()


@cli.group()
def report():
    """Generate research reports."""
    pass


@report.command("full")
@click.pass_context
def report_full(ctx):
    """Generate a full treatment compendium report."""
    from eds_researcher.memory.database import Database
    from eds_researcher.reporter.full_report import generate_full_report

    config = _load_config(ctx.obj["config"])
    db = Database(config["database"]["path"])
    try:
        output_dir = config.get("reports", {}).get("output_dir", "data/reports")
        path = generate_full_report(db, output_dir)
        click.echo(f"Full report generated: {path}")
    finally:
        db.close()


@report.command("delta")
@click.option("--days", "-d", default=7, help="Number of days to look back")
@click.pass_context
def report_delta(ctx, days):
    """Generate a delta report showing recent changes."""
    from eds_researcher.memory.database import Database
    from eds_researcher.reporter.delta_report import generate_delta_report

    config = _load_config(ctx.obj["config"])
    db = Database(config["database"]["path"])
    try:
        output_dir = config.get("reports", {}).get("output_dir", "data/reports")
        since = date.today() - timedelta(days=days)
        path = generate_delta_report(db, output_dir, since=since)
        click.echo(f"Delta report generated: {path}")
    finally:
        db.close()


@cli.command()
@click.option("--weekday", default=1, help="Day of week (1=Mon, 7=Sun)")
@click.option("--hour", default=9, help="Hour of day (0-23)")
@click.pass_context
def schedule(ctx, weekday, hour):
    """Set up weekly scheduled runs via macOS launchd."""
    from eds_researcher.scheduler.cron_setup import install_plist

    plist_path = install_plist(weekday=weekday, hour=hour)
    day_names = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
                 5: "Friday", 6: "Saturday", 7: "Sunday"}
    click.echo(f"Scheduled weekly run: {day_names.get(weekday, weekday)} at {hour:02d}:00")
    click.echo(f"Plist installed at: {plist_path}")


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize the database and seed default symptoms."""
    from eds_researcher.memory.database import Database
    from eds_researcher.memory.embeddings import EmbeddingStore
    from eds_researcher.memory.models import BodyRegion, Severity, Symptom

    config = _load_config(ctx.obj["config"])
    db = Database(config["database"]["path"])
    EmbeddingStore(config["database"]["chromadb_path"])

    # Seed symptoms
    existing = {s.name for s in db.get_all_symptoms()}
    count = 0
    for sym_cfg in config.get("symptoms", []):
        if sym_cfg["name"] not in existing:
            db.upsert_symptom(Symptom(
                name=sym_cfg["name"],
                body_region=BodyRegion(sym_cfg["body_region"]),
                severity_relevance=Severity(sym_cfg["severity"]),
            ))
            count += 1

    db.close()
    click.echo(f"Database initialized at {config['database']['path']}")
    click.echo(f"ChromaDB initialized at {config['database']['chromadb_path']}")
    click.echo(f"Seeded {count} new symptoms ({len(existing)} already existed)")


def _load_config(path: str) -> dict:
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    cli()
