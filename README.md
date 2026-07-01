# adobe-cc-font-extractor

Extracts Adobe CC fonts from the local CoreSync cache into named OTF files organized by family.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Adobe Creative Cloud with fonts synced via Adobe Fonts

## Installation

```sh
uv sync
```

## Usage

```sh
uv run adobe-cc-font-extractor [OPTIONS]
```

| Option | Short | Description |
|---|---|---|
| `--output PATH` | `-o` | Output directory (default: `output/`) |
| `--dry-run` | `-n` | Preview what would be extracted without copying |
| `--family TEXT` | `-f` | Filter by family name — repeatable |
| `--force` | | Overwrite existing files |
| `--flat` | | Disable per-family subdirectories |
| `--zip-files` | `-z` | Create one zip archive per family |
| `--font-dir PATH` | | Override the Adobe CoreSync directory |

### Examples

Extract all fonts:
```sh
uv run adobe-cc-font-extractor
```

Preview a specific family:
```sh
uv run adobe-cc-font-extractor --dry-run --family "Proxima Nova"
```

Extract multiple families and zip each one:
```sh
uv run adobe-cc-font-extractor -f "Proxima Nova" -f "Museo Sans" --zip-files
```

## Output structure

```
output/
  Proxima Nova/
    Proxima Nova Regular.otf
    Proxima Nova Bold.otf
    ...
  Museo Sans/
    Museo Sans 300.otf
    ...
  Proxima Nova.zip   # with --zip-files
```

## Supported platforms

Windows and macOS.
