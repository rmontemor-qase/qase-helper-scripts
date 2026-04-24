# Qase Helper Scripts

A collection of Python scripts for common Qase migration and maintenance
tasks. All scripts share a single Qase API client (`qase_api.py`) at the
repo root, and each script lives in its own folder with a focused README
and a minimal `config.json.example`.

## Quick start

```bash
# 1. Clone the repo
git clone <this-repo-url>
cd qase-helper-scripts

# 2. Set up a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate       # macOS / Linux
# or:  venv\Scripts\activate   # Windows

# 3. Install dependencies (one shared requirements.txt)
pip install -r requirements.txt

# 4. Pick a script and cd into its folder. config.json lives next to the
#    script (NOT at the repo root), so always run scripts from their folder.
cd csv_fixer
cp config.json.example config.json
# …edit config.json…

# 5. Run it — from inside the script's folder
python csv_fixer.py --dry-run
```

> **Working directory matters.** Every script loads `./config.json`
> relative to the current directory. Always `cd` into the script's folder
> before running its commands. Each per-script README repeats this so you
> can't miss it.

## Available scripts

| Folder | Purpose |
|---|---|
| [`csv_fixer/`](./csv_fixer/) | Fix broken CSV file references in test cases (e.g. `![file.csv](url)` → `[file.csv](url)`). |
| [`fix_html_tags/`](./fix_html_tags/) | Strip leftover HTML tags from test case text fields. |
| [`remove_attachment_references/`](./remove_attachment_references/) | Remove broken `[![attachment](...)](...)` markdown left behind by imports. |
| [`field_migration/`](./field_migration/) | Copy content from a system field (e.g. `preconditions`) into a custom field and clear the source. |
| [`update_field_from_csv/`](./update_field_from_csv/) | Bulk-update a custom field on test cases using values from a CSV. |
| [`link_jira_issues/`](./link_jira_issues/) | Extract JIRA keys from a test case's refs and attach them as external issues. |
| [`delete_custom_fields/`](./delete_custom_fields/) | **⚠ Destructive.** Delete every custom field in a workspace. |
| [`delete_attachments_by_size/`](./delete_attachments_by_size/) | **⚠ Destructive.** Delete every attachment in a workspace that matches an exact byte size. |

## Running against every project in the workspace

Every per-project script accepts `project_code: "all"` (or `--project all`
on the CLI). In that mode the script:

1. Fetches every project in the workspace via `GET /project`.
2. Prints the list of project codes.
3. Asks for a `yes` confirmation before making any changes (skipped on
   `--dry-run`, since nothing is being written).
4. Runs the single-project logic once per project and prints a
   workspace-wide aggregate summary at the end.

The two destructive workspace scripts (`delete_custom_fields`,
`delete_attachments_by_size`) are already workspace-level by nature —
they operate on every project in the workspace without this flag.

## Getting a Qase API token

Generate a token at **https://app.qase.io/user/api/token** (or, for a
dedicated instance, under **Apps → API tokens**). Paste it into the
`api_token` field of the `config.json` you create inside the script folder.

## Repo layout

```
.
├── README.md                          # this file
├── qase_api.py                        # shared Qase API client (single source)
├── requirements.txt                   # shared dependency list
├── .gitignore
│
├── csv_fixer/
│   ├── README.md
│   ├── config.json.example
│   └── csv_fixer.py
├── fix_html_tags/
├── remove_attachment_references/
├── field_migration/
├── update_field_from_csv/
├── link_jira_issues/
├── delete_custom_fields/
└── delete_attachments_by_size/
```

Each script's first few lines add the repo root to `sys.path` so
`from qase_api import …` resolves no matter where the script is launched
from. Clients don't need to know about this — it just works.
