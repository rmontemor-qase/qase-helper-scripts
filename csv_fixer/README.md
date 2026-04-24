# CSV Reference Fixer

Fixes broken CSV file references in Qase test cases.

During data imports, CSV attachments can end up rendered as images in Markdown
(e.g. `![file.csv](url)` or fully-escaped `\!\[file\.csv\]\(url\)`). This
script scans every test case in a project and rewrites those broken references
to proper Markdown links (`[file.csv](url)`). It checks `description`,
`preconditions`, `postconditions`, every step field, and every custom field.

## What it changes

- `![filename.csv](url)` → `[filename.csv](url)`
- `\![filename.csv](url)` → `[filename.csv](url)`
- `\!\[filename\.csv\]\(url\)` → `[filename.csv](url)`

## Requirements

- Python 3.8+
- Install dependencies once for the whole repo (from the repo root):

  ```bash
  pip install -r requirements.txt
  ```

## Setup

`config.json` lives inside **this folder** (next to `csv_fixer.py`), *not*
at the repo root. From the repo root:

```bash
cd csv_fixer
cp config.json.example config.json
```

Then fill in your Qase API token and project code:

```json
{
  "host": "api.qase.io",
  "api_token": "your-api-token-here",
  "project_code": "YOUR_PROJECT_CODE"
}
```

### Config fields

| Field | Required | Description |
|---|---|---|
| `host` | No | Qase API host. Default `api.qase.io`. Use your dedicated host if applicable (e.g. `api-yourcompany.qase.io`). |
| `api_token` | Yes | Qase API token. Create one under **Apps → API tokens**. |
| `project_code` | Yes | Project code (the short code shown in Qase, e.g. `DEMO`). |

## Usage

> Run the commands below from **inside this folder**. If you're not
> already here, `cd csv_fixer/` from the repo root first.

```bash
# Preview changes without modifying any test case
python csv_fixer.py --dry-run

# Apply the fixes
python csv_fixer.py

# Show per-case detail
python csv_fixer.py --verbose
```

### Run against every project in the workspace

Set `project_code` to `"all"` (or pass `--project all`) to scan every
project the API token can see. Before any writes happen the script prints
the list of project codes it found and asks for a `yes` confirmation. The
confirmation prompt is skipped in `--dry-run` mode (nothing is being
modified) but the project list is still printed.

```bash
python csv_fixer.py --project all --dry-run
python csv_fixer.py --project all
```

At the end you get a single workspace-wide summary aggregated across
every project.

### Command-line options

- `--config PATH` — Path to config file (default: `config.json`).
- `--token TOKEN` — Override `api_token` from config.
- `--project CODE` — Override `project_code` from config. Use `all` to run against every project in the workspace.
- `--host HOST` — Override `host` from config.
- `--dry-run` — Analyze only; no API writes.
- `--verbose`, `-v` — Print details for every test case.

## Output

The script prints a summary at the end:

```
Total test cases: 1234
Cases needing fixes: 87
Cases fixed: 87
Errors: 0
```
