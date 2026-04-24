# Remove Attachment References

Removes leftover attachment reference patterns from Qase test cases. This is
most useful after a migration from TestRail (or similar) that leaves broken
image/link markup in the text, such as:

```
[![attachment](https://.../attachment/HASH/attachment)](index.php?/attachments/get/123)
![attachment](https://.../attachment/HASH/attachment)
```

The script strips both shapes from every text field, then tidies up whitespace
(collapses extra blank lines).

## What it changes

It scans and cleans up the following fields on every test case:

- `description`
- `preconditions`
- `postconditions`
- Every step's `action`, `expected_result`, and `data` (including nested steps)
- All custom fields

If cleaning empties a step's `action`, it is set to `.` to satisfy Qase's
"Action field is required" validation. If the API still rejects the update
because of an empty action, the script automatically retries with the same
patch applied to every step.

## Requirements

- Python 3.8+
- Install dependencies once for the whole repo (from the repo root):

  ```bash
  pip install -r requirements.txt
  ```

## Setup

`config.json` lives inside **this folder** (next to
`remove_attachment_references.py`), *not* at the repo root. From the repo
root:

```bash
cd remove_attachment_references
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
| `host` | No | Qase API host. Default `api.qase.io`. |
| `api_token` | Yes | Qase API token. |
| `project_code` | Yes | Project code (e.g. `DEMO`). |

## Usage

> Run the commands below from **inside this folder**. If you're not
> already here, `cd remove_attachment_references/` from the repo root
> first.

```bash
# Preview changes without modifying any test case
python remove_attachment_references.py --dry-run

# Apply the changes
python remove_attachment_references.py

# Show per-case detail
python remove_attachment_references.py --verbose
```

### Run against every project in the workspace

Set `project_code` to `"all"` (or pass `--project all`) to clean up every
project the API token can see. The script prints the list of discovered
project codes and asks for a `yes` confirmation before any writes
(skipped in `--dry-run`).

```bash
python remove_attachment_references.py --project all --dry-run
python remove_attachment_references.py --project all
```

A workspace-wide aggregate summary is printed at the end.

### Command-line options

- `--config PATH` — Path to config file (default: `config.json`).
- `--token TOKEN` — Override `api_token` from config.
- `--project CODE` — Override `project_code` from config. Use `all` to run against every project in the workspace.
- `--host HOST` — Override `host` from config.
- `--dry-run` — Analyze only; no API writes.
- `--verbose`, `-v` — Print details for every test case.
