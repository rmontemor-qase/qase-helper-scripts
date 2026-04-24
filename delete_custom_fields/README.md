# Delete All Custom Fields

Deletes **every** custom field in a Qase workspace.

---

## ⚠️ DESTRUCTIVE AND IRREVERSIBLE ⚠️

**Read this before you run the script.**

- This script deletes **every custom field** found in the workspace associated
  with the provided API token. It operates at the **workspace level** — not at
  a single project — so *all* projects in the workspace are affected.
- Deleting a custom field in Qase **permanently removes the field and every
  value stored in it on every test case, test run, defect, and plan**. There
  is **no undo** and no built-in way to restore the data.
- There is no filter, include-list, or exclude-list. If you run this, the
  script asks for a single `yes` confirmation and then deletes them all.
- Intended use: cleaning up a throwaway / sandbox workspace, or wiping custom
  fields before a fresh migration. **Never run this against a production
  workspace unless you are absolutely certain that is what you want.**

Before running, **always**:

1. Confirm you are pointing at the correct workspace (check `host` and
   `api_token` carefully).
2. Take a backup / export of any data you might want later.
3. Tell the workspace owner you are about to do this.

---

## Requirements

- Python 3.8+
- Install dependencies once for the whole repo (from the repo root):

  ```bash
  pip install -r requirements.txt
  ```

## Setup

`config.json` lives inside **this folder** (next to
`delete_custom_fields.py`), *not* at the repo root. From the repo root:

```bash
cd delete_custom_fields
cp config.json.example config.json
```

Then fill in the API token for the workspace you want to clean:

```json
{
  "host": "api.qase.io",
  "api_token": "your-api-token-here"
}
```

### Config fields

| Field | Required | Description |
|---|---|---|
| `host` | No | Qase API host. Default `api.qase.io`. Use your dedicated host if applicable. |
| `api_token` | Yes | Qase API token for the workspace whose custom fields will be deleted. |

No `project_code` is needed — custom fields are a workspace-level resource.

## Usage

> Run the command below from **inside this folder**. If you're not
> already here, `cd delete_custom_fields/` from the repo root first.

```bash
python delete_custom_fields.py
```

The script will:

1. Fetch every custom field in the workspace and print the list.
2. Ask for confirmation: `Are you sure you want to delete all N custom
   field(s)? (yes/no):`
3. Only if you type `yes` will it start deleting.

There is **no dry-run mode**. To preview what would be deleted, list the
custom fields yourself first (for example in the Qase UI, or via a quick
`GET /custom_field` call) before running this script.

## Output

```
Total custom fields: 42
Successfully deleted: 42
Failed: 0
```
