# Update Field From CSV

Updates a single **custom field** on Qase test cases using the contents of a
CSV file. Useful when you have bulk-edited values outside of Qase (for example
in a spreadsheet) and need to push them back into the project.

## What it does

1. Reads the CSV file you pass as the first argument.
2. For each row, looks up the test case by its Qase code (the `ID` column
   in the CSV, e.g. `C123` or `123`).
3. Strips HTML tags from the value read from the CSV column.
4. Writes that value into the configured custom field on the matching test
   case. The CSV is treated as the source of truth — values are overwritten
   even if they already match.

Matching is tolerant of the `C` prefix: `C123` in the CSV will match a case
whose code is `123` or `C123`, and vice versa.

## CSV format

- Must be comma-separated with a header row.
- Must contain an `ID` column with the Qase test case code.
- Must contain the column named in `csv_column_name` (defaults to the field
  name).

Example:

```csv
ID,Postconditions
C123,"Logout and clear cookies."
C124,"Restore the DB from the pre-run snapshot."
```

## Requirements

- Python 3.8+
- Install dependencies once for the whole repo (from the repo root):

  ```bash
  pip install -r requirements.txt
  ```

- The custom field must already exist in the Qase project.

## Setup

`config.json` lives inside **this folder** (next to
`update_field_from_csv.py`), *not* at the repo root. From the repo root:

```bash
cd update_field_from_csv
cp config.json.example config.json
```

Then fill in your Qase API token, project code, and the CSV/field
mapping:

```json
{
  "host": "api.qase.io",
  "api_token": "your-api-token-here",
  "project_code": "YOUR_PROJECT_CODE",
  "csv_field_name": "Postconditions",
  "csv_column_name": "Postconditions",
  "csv_field_id": null
}
```

### Config fields

| Field | Required | Description |
|---|---|---|
| `host` | No | Qase API host. Default `api.qase.io`. |
| `api_token` | Yes | Qase API token. |
| `project_code` | Yes | Project code (e.g. `DEMO`). |
| `csv_field_name` | Yes | Name of the **Qase custom field** to update. Defaults to `Postconditions` if not provided. |
| `csv_column_name` | No | Name of the **CSV column** to read. Defaults to `csv_field_name`. |
| `csv_field_id` | No | Custom field ID if you already know it. Set to `null` to look it up by name. |

## Usage

> Run the commands below from **inside this folder**. If you're not
> already here, `cd update_field_from_csv/` from the repo root first.
> The CSV path is relative to the current directory, so place your CSV
> file here (or use an absolute path).

```bash
# Preview changes without modifying any test case
python update_field_from_csv.py mydata.csv --dry-run

# Apply the updates
python update_field_from_csv.py mydata.csv

# Override field / column at the command line
python update_field_from_csv.py mydata.csv \
  --field-name "Preconditions" \
  --csv-column "Preconditions" \
  --dry-run
```

### Run against every project in the workspace

Set `project_code` to `"all"` (or pass `--project all`) to apply the same
CSV to every project the API token can see. The script:

1. Lists every project discovered in the workspace.
2. Asks for a `yes` confirmation before any writes (skipped in
   `--dry-run`).
3. Iterates per project and updates the rows whose test case code lives
   in that project. Rows that don't live there are just "not matched
   here" — that's expected.
4. Skips projects where the target custom field doesn't exist (with a
   warning) and continues.
5. Prints a workspace-wide aggregate at the end, including a
   **`CSV rows not found in workspace`** count (rows that weren't
   matched in *any* project — these are the truly-missing test case
   codes).

```bash
python update_field_from_csv.py mydata.csv --project all --dry-run
python update_field_from_csv.py mydata.csv --project all
```

> `csv_field_id` / `--field-id` is project-specific and is silently
> ignored in `"all"` mode — the field is always resolved by name per
> project.

### Command-line options

- `csv_file` — Path to the CSV file (positional, required).
- `--config PATH` — Path to config file (default: `config.json`).
- `--token TOKEN` — Override `api_token` from config.
- `--project CODE` — Override `project_code` from config. Use `all` to run against every project in the workspace.
- `--host HOST` — Override `host` from config.
- `--field-name NAME` — Override `csv_field_name` from config.
- `--field-id ID` — Override `csv_field_id` from config.
- `--csv-column NAME` — Override `csv_column_name` from config.
- `--dry-run` — Analyze only; no API writes.
- `--verbose`, `-v` — Print details for every row.

## Output

The script prints a summary at the end:

```
Total CSV rows:          1234
Matched test cases:       1230
Updated:                  1230
Not found in Qase:           4
Errors:                      0
```
