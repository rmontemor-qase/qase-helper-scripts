# Fix HTML Tags

Removes HTML tags (e.g. `<p>`, `<br>`, `<span>`) from every text field in Qase
test cases. This is useful when content was imported from a system that stored
HTML and the tags are showing up as literal text in Qase.

## What it changes

Strips any `<tag>` / `</tag>` occurrences from:

- `description`
- `preconditions`
- `postconditions`
- Every step's `action`, `expected_result`, and `data` fields
- All custom fields

Line breaks are preserved; extra blank lines are collapsed to at most two.

## Requirements

- Python 3.8+
- Install dependencies once for the whole repo (from the repo root):

  ```bash
  pip install -r requirements.txt
  ```

## Setup

`config.json` lives inside **this folder** (next to `fix_html_tags.py`),
*not* at the repo root. From the repo root:

```bash
cd fix_html_tags
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
| `host` | No | Qase API host. Default `api.qase.io`. Use your dedicated host if applicable. |
| `api_token` | Yes | Qase API token. |
| `project_code` | Yes | Project code (e.g. `DEMO`). |

## Usage

> Run the commands below from **inside this folder**. If you're not
> already here, `cd fix_html_tags/` from the repo root first.

```bash
# Preview changes without modifying any test case
python fix_html_tags.py --dry-run

# Apply the changes
python fix_html_tags.py

# Show per-case detail
python fix_html_tags.py --verbose
```

### Run against every project in the workspace

Set `project_code` to `"all"` (or pass `--project all`) to strip HTML
tags across every project the API token can see. The script prints the
list of discovered project codes and asks for a `yes` confirmation before
any writes (skipped in `--dry-run`).

```bash
python fix_html_tags.py --project all --dry-run
python fix_html_tags.py --project all
```

A workspace-wide aggregate summary is printed at the end.

### Command-line options

- `--config PATH` — Path to config file (default: `config.json`).
- `--token TOKEN` — Override `api_token` from config.
- `--project CODE` — Override `project_code` from config. Use `all` to run against every project in the workspace.
- `--host HOST` — Override `host` from config.
- `--dry-run` — Analyze only; no API writes.
- `--verbose`, `-v` — Print details for every test case.

## Output

A summary is printed at the end, including a breakdown of how many cases were
fixed per field type (description, preconditions, postconditions, steps, custom
fields).
