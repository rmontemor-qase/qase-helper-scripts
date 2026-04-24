# Delete Attachments by Size

Deletes every attachment in a Qase workspace whose file size (in bytes)
matches a specific target value. Useful for removing junk/placeholder
attachments (e.g. TestRail's broken 157 KB "attachment" placeholder files)
after an import.

---

## ⚠️ DESTRUCTIVE AND IRREVERSIBLE ⚠️

**Read this before you run the script.**

- This script deletes attachments at the **workspace level** — not in a
  single project. Every matching attachment in the workspace for the
  provided API token will be deleted.
- **Deleted attachments cannot be recovered.** Qase does not keep a trash /
  recycle bin for attachments. If a real (non-placeholder) file happens to
  be the same exact size as `TARGET_SIZE`, it will also be deleted without
  warning.
- The size match is **exact, in bytes**. A file that is one byte different
  will not be touched.
- Use only when you have verified that the files of that exact size are
  genuinely junk.

Before running, **always**:

1. List a few attachments with the target size in the Qase UI and confirm
   they are the ones you want gone.
2. Confirm you are pointing at the correct workspace (check `host` and
   `api_token`).
3. Tell the workspace owner you are about to do this.

---

## Configure the target size

The target size is a **constant at the top of the script** because it is
usually set once per cleanup job:

```python
# delete_attachments_by_size.py
TARGET_SIZE = 157010   # bytes. Edit this before running.
NUM_WORKERS = 10       # parallel delete workers
```

Open `delete_attachments_by_size.py`, change `TARGET_SIZE` to the byte count
you want to target, save, and run the script. You can also reduce
`NUM_WORKERS` if you are worried about API rate limits.

## Requirements

- Python 3.8+
- Install dependencies once for the whole repo (from the repo root):

  ```bash
  pip install -r requirements.txt
  ```

## Setup

`config.json` lives inside **this folder** (next to
`delete_attachments_by_size.py`), *not* at the repo root. From the repo
root:

```bash
cd delete_attachments_by_size
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
| `api_token` | Yes | Qase API token for the workspace whose attachments will be deleted. |

No `project_code` is needed — attachments are a workspace-level resource.

## Usage

> Run the command below from **inside this folder**. If you're not
> already here, `cd delete_attachments_by_size/` from the repo root
> first.

```bash
python delete_attachments_by_size.py
```

The script will:

1. List every attachment in the workspace.
2. Filter those whose `size` equals `TARGET_SIZE`.
3. Show the first 10 matches (hash, filename, size).
4. Ask for confirmation: `Are you sure you want to delete all N
   attachment(s) with size X? (yes/no):`
5. Only if you type `yes` will it start deleting (in parallel across
   `NUM_WORKERS`).

There is **no dry-run flag**. To preview, you can temporarily change the
`input(...)` prompt response or just cancel at the confirmation step after
reviewing the list it prints.

## Output

```
Total attachments checked: 12482
Attachments with size 157010: 3217
Successfully deleted: 3217
Failed: 0
Workers used: 10
```
