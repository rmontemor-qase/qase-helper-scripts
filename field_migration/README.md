# Field Migration

Copies the value of one field into another field on every test case in a
Qase project. Both the source and the destination can be either a **system**
field (`description`, `preconditions`, `postconditions`) or a **custom**
field — any combination is allowed:

- `system → custom`
- `custom → system`
- `system → system`
- `custom → custom`

For each test case:

1. Read the source field.
2. If it has non-empty content, write that value into the destination field.
3. Optionally clear the source field (off by default).

Cases with an empty source field are left untouched.

## Requirements

- Python 3.8+
- Install dependencies once for the whole repo (from the repo root):

  ```bash
  pip install -r requirements.txt
  ```

- The destination **field must already exist** in the Qase project/
  workspace. The script does not create it for you.

## Setup

`config.json` lives inside **this folder** (next to `field_migration.py`),
*not* at the repo root. From the repo root:

```bash
cd field_migration
cp config.json.example config.json
```

Then fill in your Qase API token, project code, and the fields to migrate:

```json
{
  "host": "api.qase.io",
  "api_token": "your-api-token-here",
  "project_code": "YOUR_PROJECT_CODE",
  "source_field": "preconditions",
  "destination_field": "Preconditions",
  "clear_source": false
}
```

### Config fields

| Field | Required | Description |
|---|---|---|
| `host` | No | Qase API host. Default `api.qase.io`. |
| `api_token` | Yes | Qase API token. |
| `project_code` | Yes | Project code (e.g. `DEMO`). |
| `source_field` | Yes | Name of the source field. Can be a system field title/slug (e.g. `preconditions`, `description`) **or** a custom field title. |
| `destination_field` | Yes | Name of the destination field. Can be a system field title/slug **or** a custom field title. |
| `clear_source` | No | If `true`, the source field is blanked on every migrated case. Defaults to `false` (source is preserved). |

All of these can also be overridden on the command line.

### Field resolution

- Names are matched case-insensitively.
- A system field matches on its **title** or **slug**.
- A custom field matches on its **title**.
- If a name matches **both** a system field and a custom field, the script
  prints the candidates and asks you which one to use (type the slug for
  the system field, or the numeric id for the custom field). You only see
  this prompt when the name is genuinely ambiguous.

## Usage

> Run the commands below from **inside this folder**. If you're not
> already here, `cd field_migration/` from the repo root first.

```bash
# Preview changes without modifying any test case
python field_migration.py --dry-run

# Apply the migration
python field_migration.py

# Show per-case detail
python field_migration.py --verbose

# Also clear the source field after copying
python field_migration.py --clear-source
```

### Override fields from the command line

```bash
# System -> custom
python field_migration.py \
  --source-field description \
  --destination-field "Test Description" \
  --dry-run

# Custom -> system
python field_migration.py \
  --source-field "Legacy Preconditions" \
  --destination-field preconditions \
  --clear-source \
  --dry-run

# Custom -> custom (e.g. consolidating two custom fields)
python field_migration.py \
  --source-field "Old Owner" \
  --destination-field "Owner" \
  --clear-source
```

### Run against every project in the workspace

Set `project_code` to `"all"` (or pass `--project all`) to run the same
migration on every project the API token can see. The script:

1. Lists every project discovered in the workspace.
2. Asks for a `yes` confirmation before any writes (skipped in
   `--dry-run`).
3. Resolves the source and destination fields **in the first project**,
   prompting you if a name is ambiguous (matches both a system and a
   custom field).
4. Remembers your choice of **kind** (`system` / `custom`) and reuses it
   silently for every subsequent project, even though the custom field
   IDs themselves differ per project.
5. Skips projects where the field doesn't exist (with a warning) and
   continues.

```bash
python field_migration.py --project all --dry-run
python field_migration.py --project all --clear-source
```

A workspace-wide aggregate summary is printed at the end.

### Command-line options

- `--config PATH` — Path to config file (default: `config.json`).
- `--token TOKEN` — Override `api_token` from config.
- `--project CODE` — Override `project_code` from config. Use `all` to run against every project in the workspace.
- `--host HOST` — Override `host` from config.
- `--source-field NAME` — Override `source_field` from config.
- `--destination-field NAME` — Override `destination_field` from config.
- `--clear-source` — Clear the source field after copying (overrides config).
- `--no-clear-source` — Leave the source field untouched (overrides config).
- `--dry-run` — Analyze only; no API writes.
- `--verbose`, `-v` — Print details for every test case.

## Output

A progress bar and a final summary:

```
Total test cases:          1234
Cases needing migration:    540
Cases migrated:             540
Cases skipped:                0
Errors:                       0
```
