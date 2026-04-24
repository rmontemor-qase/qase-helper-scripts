# Link JIRA Issues

Extracts JIRA issue keys (e.g. `PROJ-123`) from a test case's **refs** field
and attaches them to the case as external issues using Qase's External Issues
API. Works on a single project or, by setting `project_code` to `"all"`, every
project in the workspace (in parallel).

## What it does

1. Fetches all test cases from the configured project (or every project).
2. Reads the refs field for each case. By default this is the built-in
   system `refs`/`references`, but you can point it at a custom field via
   `jira_refs_field` / `jira_refs_field_id`.
3. Extracts any strings matching the JIRA key pattern `[A-Z][A-Z0-9]+-\d+`.
4. Batches them and calls Qase's `POST /case/{code}/external-issue/attach`
   endpoint. Failed batches are automatically retried one case at a time so
   that a single bad issue key doesn't drop the whole batch.
5. Writes a full log to `logs/link_jira_<timestamp>.log` (path configurable),
   including a list of JIRA project keys whose issues couldn't be found.

## Requirements

- Python 3.8+
- Install dependencies once for the whole repo (from the repo root):

  ```bash
  pip install -r requirements.txt
  ```

- The Qase project must have the JIRA integration already configured
  (**Integrations → JIRA Cloud / JIRA Server**) so that external issues can
  actually be resolved.

## Setup

`config.json` lives inside **this folder** (next to
`link_jira_issues.py`), *not* at the repo root. From the repo root:

```bash
cd link_jira_issues
cp config.json.example config.json
```

Then fill in your Qase API token and project code.

```json
{
  "host": "api.qase.io",
  "api_token": "your-api-token-here",
  "project_code": "YOUR_PROJECT_CODE",
  "jira_refs_field": "refs",
  "jira_refs_field_id": null,
  "parallel_workers": 8,
  "calls_per_minute": 1000,
  "log_file": "logs/link_jira_run.log"
}
```

### Config fields

| Field | Required | Description |
|---|---|---|
| `host` | No | Qase API host. Default `api.qase.io`. |
| `api_token` | Yes | Qase API token. |
| `project_code` | Yes | Project code (e.g. `DEMO`). Use `"all"` to run against every project in the workspace (you'll be shown the list and asked to confirm before any writes). |
| `jira_refs_field` | No | Name of the field containing JIRA references. Defaults to the system `refs`/`references`. Set to a custom field title to read from a custom field instead. |
| `jira_refs_field_id` | No | Custom field ID for the refs field. If set, this takes precedence over `jira_refs_field`. Use `null` to search by name. |
| `parallel_workers` | No | Parallel workers used when `project_code` is `"all"`. Default `8`. |
| `calls_per_minute` | No | Global API rate-limit cap. Default `1000`. |
| `log_file` | No | Path to the log file. Default `logs/link_jira_<timestamp>.log`. |

## Usage

> Run the commands below from **inside this folder**. If you're not
> already here, `cd link_jira_issues/` from the repo root first. The log
> file path in the config is also resolved relative to this folder, so
> logs end up in `link_jira_issues/logs/` by default.

```bash
# Preview what would be attached
python link_jira_issues.py --dry-run

# Attach JIRA issues
python link_jira_issues.py

# Run against every project in the workspace
python link_jira_issues.py --project all

# JIRA Server instead of JIRA Cloud
python link_jira_issues.py --type jira-server

# Smaller batches, verbose log
python link_jira_issues.py --batch-size 25 --verbose
```

### Command-line options

- `--config PATH` — Path to config file (default: `config.json`).
- `--token TOKEN` — Override `api_token` from config.
- `--project CODE` — Override `project_code` from config. Use `all` for every project.
- `--host HOST` — Override `host` from config.
- `--type {jira-cloud,jira-server}` — JIRA instance type. Default `jira-cloud`.
- `--batch-size N` — Cases per attach batch. Default `50`.
- `--refs-field NAME` — Override `jira_refs_field` from config.
- `--refs-field-id ID` — Override `jira_refs_field_id` from config.
- `--workers N` — Override `parallel_workers`.
- `--calls-per-minute N` — Override `calls_per_minute`.
- `--log-file PATH` — Override `log_file`.
- `--dry-run` — Analyze only; no attach requests.
- `--verbose`, `-v` — Verbose logging (to the log file).

## Output

Progress is printed to stdout:

```
[=========>-----] 48.2% 580/1203 | attached: 512 | errors: 3
```

A full log is written to `logs/link_jira_<timestamp>.log`. At the end of the
run it also contains a JSON array of the JIRA project keys that the Qase
integration was unable to resolve — share this list with your JIRA admin to
fix missing integrations.
