import os
import platform
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from importlib.metadata import version as get_version
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

import typer
from fontTools.ttLib import TTFont
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

FONT_SPECIFIER_VARIATION_ID = 4
FONT_SPECIFIER_NAME_ID = 1

console = Console()
app = typer.Typer(
    help="Extract Adobe CC fonts to OTF files organized by family folder.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(
            f"adobe-cc-font-extractor {get_version('adobe-cc-font-extractor')}"
        )
        raise typer.Exit()


@dataclass
class FontEntry:
    font_id: str
    full_name: str
    family_name: str
    variation_name: str
    is_variable: bool
    install_state: str


@dataclass
class ExtractionStats:
    extracted: int = 0
    skipped: int = 0
    missing: int = 0
    errors: int = 0
    families: dict[str, list[str]] = field(default_factory=dict)
    family_files: dict[str, list[Path]] = field(default_factory=dict)


def get_adobe_font_path() -> Path:
    if platform.system() == "Windows":
        return Path(os.path.expandvars(r"%APPDATA%\Adobe\CoreSync\plugins\livetype"))
    elif platform.system() == "Darwin":
        return Path(
            os.path.expandvars(
                "$HOME/Library/Application Support/Adobe/CoreSync/plugins/livetype"
            )
        )
    else:
        console.print(f"[red]Unsupported platform:[/red] {platform.system()}")
        raise typer.Exit(1)


def sanitize_path_component(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ")


def parse_entitlements(manifest: Path) -> list[FontEntry]:
    root = ElementTree.parse(manifest).getroot()
    entries = []
    for font in root.find("fonts").findall("font"):
        font_id = font.find("id").text
        props = font.find("properties")
        entries.append(
            FontEntry(
                font_id=font_id,
                full_name=props.findtext("fullName", "").strip(),
                family_name=props.findtext("familyName", "").strip(),
                variation_name=props.findtext("variationName", "").strip(),
                is_variable=props.findtext("isVariable", "false").lower() == "true",
                install_state=props.findtext("installState", ""),
            )
        )
    return entries


def find_font_file(font_id: str, font_path: Path) -> Optional[Path]:
    for candidate in ("r", "t", "w"):
        source = font_path / candidate / font_id
        if source.exists():
            return source
    return None


@app.command()
def extract(
    _version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        is_eager=True,
        callback=_version_callback,
        help="Show version and exit",
    ),
    output: Path = typer.Option(
        Path("Fonts"), "--output", "-o", help="Output directory"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be extracted without copying files",
    ),
    family: Optional[list[str]] = typer.Option(
        None, "--family", "-f", help="Filter by family name (repeatable)"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
    flat: bool = typer.Option(
        False,
        "--flat",
        help="Put all fonts in output dir without family subdirectories",
    ),
    zip_files: bool = typer.Option(
        False,
        "--zip-files",
        "-z",
        help="Create one zip archive per family in the output directory",
    ),
    font_dir: Optional[Path] = typer.Option(
        None, "--font-dir", help="Override the Adobe CoreSync font directory"
    ),
) -> None:
    """Extract Adobe CC fonts to OTF files, organized in per-family subdirectories."""
    font_path = font_dir or get_adobe_font_path()
    manifest = font_path / "c" / "entitlements.xml"

    if not manifest.exists():
        console.print(f"[red]Manifest not found:[/red] {manifest}")
        raise typer.Exit(1)

    console.print(f"[dim]Reading entitlements from[/dim] {manifest}")
    entries = parse_entitlements(manifest)

    if family:
        filter_set = {f.lower() for f in family}
        entries = [e for e in entries if e.family_name.lower() in filter_set]

    if not entries:
        console.print("[yellow]No fonts matched the given filters.[/yellow]")
        raise typer.Exit(0)

    if not dry_run:
        output.mkdir(parents=True, exist_ok=True)

    stats = ExtractionStats()

    with Progress(
        SpinnerColumn(),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Processing...", total=len(entries))

        for entry in entries:
            progress.update(task, description=f"[dim]{entry.full_name[:50]}[/dim]")

            source = find_font_file(entry.font_id, font_path)
            if source is None:
                stats.missing += 1
                progress.advance(task)
                continue

            safe_family = sanitize_path_component(entry.family_name)
            safe_full = sanitize_path_component(entry.full_name)
            dest_dir = output if flat else output / safe_family
            destination = dest_dir / f"{safe_full}.otf"

            stats.families.setdefault(entry.family_name, [])
            stats.family_files.setdefault(entry.family_name, [])

            if destination.exists() and not force:
                stats.skipped += 1
                progress.advance(task)
                continue

            try:
                TTFont(file=source)
            except Exception as exc:
                console.print(
                    f"[yellow]  Invalid font file:[/yellow] {entry.full_name} — {exc}"
                )
                stats.errors += 1
                progress.advance(task)
                continue

            if not dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(source, destination)

            stats.families[entry.family_name].append(entry.variation_name)
            stats.family_files[entry.family_name].append(destination)
            stats.extracted += 1
            progress.advance(task)

        zipped = 0
        progress.reset(task, total=len(stats.family_files))
        if zip_files and not dry_run:
            for family_name, paths in stats.family_files.items():
                progress.update(task, description=f"[dim]{family_name[:50]}[/dim]")
                if not paths:
                    continue
                zip_path = output / f"{sanitize_path_component(family_name)}.zip"
                with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for p in set(paths):
                        zf.write(p, arcname=p.name)
                zipped += 1
                progress.advance(task)

    _print_report(stats, dry_run, zipped)

def _print_report(stats: ExtractionStats, dry_run: bool, zipped: int = 0) -> None:
    extracted_families = {fam: vars for fam, vars in stats.families.items() if vars}

    if extracted_families:
        table = Table(
            title="Fonts Extracted by Family", show_header=True, header_style="bold"
        )
        table.add_column("Family", style="cyan", no_wrap=True)
        table.add_column("Variations", style="green")
        table.add_column("#", justify="right", style="bold")

        for fam_name, variations in sorted(extracted_families.items()):
            table.add_row(fam_name, ", ".join(sorted(variations)), str(len(variations)))

        console.print()
        console.print(table)

    console.print()
    action = "Would extract" if dry_run else "Extracted"
    console.print(
        f"[bold green]{action}:[/bold green] {stats.extracted} fonts across {len(extracted_families)} families"
    )
    if stats.skipped:
        console.print(f"[yellow]Skipped (already exist):[/yellow] {stats.skipped}")
    if stats.missing:
        console.print(f"[red]Missing from filesystem:[/red] {stats.missing}")
    if stats.errors:
        console.print(f"[red]Errors:[/red] {stats.errors}")
    if zipped:
        console.print(
            f"[bold cyan]Zipped:[/bold cyan] {zipped} family archives created"
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
