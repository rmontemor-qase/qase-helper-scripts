"""
Qase API Client

Handles all API interactions with the Qase API.
"""

import json
import os
import sys
import requests
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_QASE_HOST = "api.qase.io"


def qase_base_url_from_host(host: Optional[str] = None) -> str:
    """
    Build the Qase API base URL (…/v1).

    If host is missing, uses api.qase.io. Accepts a hostname (api-yourcompany.qase.io)
    or a full URL (https://api-yourcompany.qase.io/).
    """
    if host is None or not str(host).strip():
        return f"https://{DEFAULT_QASE_HOST}/v1"
    h = str(host).strip()
    if h.startswith("http://") or h.startswith("https://"):
        base = h.rstrip("/")
    else:
        base = f"https://{h.rstrip('/')}"
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def resolve_qase_base_url(
    cli_host: Optional[str] = None,
    config_dict: Optional[Dict[str, Any]] = None,
    config_path: str = "config.json",
) -> str:
    """
    Resolve API base URL: CLI --host overrides config host, then config file, then default.
    """
    if cli_host:
        return qase_base_url_from_host(cli_host)
    if config_dict is not None and config_dict.get("host"):
        return qase_base_url_from_host(config_dict.get("host"))
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
            if cfg.get("host"):
                return qase_base_url_from_host(cfg.get("host"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return qase_base_url_from_host(None)


class QaseAPI:
    """Client for interacting with the Qase API."""

    def __init__(self, api_token: str, project_code: str, base_url: Optional[str] = None):
        """
        Initialize the Qase API client.

        Args:
            api_token: Qase API token
            project_code: Project code (e.g., 'CR')
            base_url: Base URL for the API (default: https://api.qase.io/v1)
        """
        if base_url is None:
            base_url = qase_base_url_from_host(None)
        self.api_token = api_token
        self.project_code = project_code
        self.base_url = base_url
        self.headers = {
            "Token": api_token,
            "accept": "application/json",
            "content-type": "application/json"
        }
        self.max_limit = 100

    def list_projects_page(
        self,
        limit: int = 100,
        offset: int = 0,
        quiet: bool = True,
        rate_limiter: Any = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Fetch one page of projects (GET /project).

        Returns:
            (entities, total) — total is workspace project count from API.
        """
        if rate_limiter is not None:
            rate_limiter.acquire()
        url = f"{self.base_url}/project"
        params = {"limit": limit, "offset": offset}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if not data.get("status"):
                return [], 0
            result = data.get("result", {})
            if isinstance(result, list):
                entities = result
                total = len(entities)
            else:
                entities = result.get("entities", []) if isinstance(result, dict) else []
                total = int(result.get("total", len(entities))) if isinstance(result, dict) else len(entities)
            return entities, total
        except requests.exceptions.RequestException as e:
            if not quiet:
                print(f"Error fetching projects: {e}")
                if hasattr(e, "response") and e.response is not None:
                    print(f"Response: {e.response.text}")
            return [], 0

    def get_all_projects(self, quiet: bool = False, rate_limiter: Any = None) -> List[Dict[str, Any]]:
        """Paginate through all projects; each entity should include 'code'."""
        all_projects: List[Dict[str, Any]] = []
        offset = 0
        limit = self.max_limit
        while True:
            entities, _ = self.list_projects_page(
                limit=limit, offset=offset, quiet=quiet, rate_limiter=rate_limiter
            )
            if not entities:
                break
            all_projects.extend(entities)
            offset += len(entities)
            if len(entities) < limit:
                break
        if not quiet:
            print(f"Total projects fetched: {len(all_projects)}")
        return all_projects

    def get_test_case_total(self, quiet: bool = True, rate_limiter: Any = None) -> int:
        """Return total test case count for this client's project_code (single GET with limit=1)."""
        if rate_limiter is not None:
            rate_limiter.acquire()
        url = f"{self.base_url}/case/{self.project_code}"
        params = {"limit": 1, "offset": 0}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if not data.get("status"):
                return 0
            result = data.get("result", {})
            total = int(result.get("total", 0))
            return total
        except requests.exceptions.RequestException as e:
            if not quiet:
                print(f"Error fetching case total for {self.project_code}: {e}")
            return 0

    def get_all_test_cases(self, quiet: bool = False, rate_limiter: Any = None) -> List[Dict[str, Any]]:
        """
        Fetch all test cases from the project using pagination.

        Returns:
            List of all test case dictionaries
        """
        all_cases = []
        offset = 0
        limit = self.max_limit

        if not quiet:
            print(f"Fetching test cases from project '{self.project_code}'...")

        while True:
            if rate_limiter is not None:
                rate_limiter.acquire()
            url = f"{self.base_url}/case/{self.project_code}"
            params = {"limit": limit, "offset": offset}

            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()

                if not data.get("status"):
                    if not quiet:
                        print(f"Error: API returned status false")
                    break

                result = data.get("result", {})
                entities = result.get("entities", [])
                total = result.get("total", 0)
                count = result.get("count", 0)

                all_cases.extend(entities)
                if not quiet:
                    print(f"Fetched {len(entities)} cases (offset: {offset}, total: {total})")

                # Check if we've fetched all cases
                if offset + count >= total or len(entities) == 0:
                    break

                offset += count

            except requests.exceptions.RequestException as e:
                if not quiet:
                    print(f"Error fetching test cases: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        print(f"Response: {e.response.text}")
                break

        if not quiet:
            print(f"Total test cases fetched: {len(all_cases)}")
        return all_cases

    def get_system_fields(self) -> List[Dict[str, Any]]:
        """
        Fetch all system field definitions.

        Returns:
            List of system field dictionaries
        """
        url = f"{self.base_url}/system_field"

        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()

            if not data.get("status"):
                print(f"Error: API returned status false")
                return []

            result = data.get("result", [])
            return result
        except requests.exceptions.RequestException as e:
            print(f"Error fetching system fields: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return []

    def get_custom_fields(self, quiet: bool = False, rate_limiter: Any = None) -> List[Dict[str, Any]]:
        """
        Fetch all custom field definitions from the workspace using pagination.

        Returns:
            List of custom field dictionaries
        """
        all_fields = []
        offset = 0
        limit = self.max_limit

        if not quiet:
            print(f"Fetching custom fields from workspace...")

        while True:
            if rate_limiter is not None:
                rate_limiter.acquire()
            url = f"{self.base_url}/custom_field"
            params = {"limit": limit, "offset": offset}

            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()

                if not data.get("status"):
                    if not quiet:
                        print(f"Error: API returned status false")
                    break

                result = data.get("result", {})
                entities = result.get("entities", [])
                total = result.get("total", 0)
                count = result.get("count", 0)

                all_fields.extend(entities)
                if not quiet:
                    print(f"Fetched {len(entities)} custom fields (offset: {offset}, total: {total})")

                # Check if we've fetched all fields
                if offset + count >= total or len(entities) == 0:
                    break

                offset += count

            except requests.exceptions.RequestException as e:
                if not quiet:
                    print(f"Error fetching custom fields: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        print(f"Response: {e.response.text}")
                break

        if not quiet:
            print(f"Total custom fields fetched: {len(all_fields)}")
        return all_fields

    def update_test_case(self, case_id: int, updates: Dict[str, Any]) -> bool:
        """
        Update a test case with the provided updates.

        Args:
            case_id: ID of the test case to update
            updates: Dictionary containing fields to update

        Returns:
            True if update was successful, False otherwise
        """
        url = f"{self.base_url}/case/{self.project_code}/{case_id}"

        try:
            response = requests.patch(url, headers=self.headers, json=updates)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error updating case {case_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return False

    def attach_external_issues(
        self, external_issue_type: str, links: List[Dict[str, Any]], quiet: bool = False
    ) -> bool:
        ok, _ = self.attach_external_issues_with_error(external_issue_type, links, quiet=quiet)
        return ok

    def attach_external_issues_with_error(
        self, external_issue_type: str, links: List[Dict[str, Any]], quiet: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Attach external issues; return (success, error_message_or_body for failures).

        Does not raise on HTTP error status so callers can parse errorMessage (e.g. missing JIRA keys).
        """
        if not links:
            return True, None

        url = f"{self.base_url}/case/{self.project_code}/external-issue/attach"
        payload = {
            "type": external_issue_type,
            "links": links
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            try:
                data = response.json() if response.text else {}
            except (ValueError, json.JSONDecodeError):
                data = {}

            if response.status_code < 400 and data.get("status"):
                return True, None

            err = (
                data.get("errorMessage")
                or data.get("error")
                or response.text
                or f"HTTP {response.status_code}"
            )
            if not quiet:
                print(f"Failed to attach external issues: {err}")
            return False, err if isinstance(err, str) else str(err)

        except requests.exceptions.RequestException as e:
            body = ""
            if hasattr(e, "response") and e.response is not None:
                body = e.response.text or ""
            msg = f"{e!s} {body}".strip()
            if not quiet:
                print(f"Exception when attaching external issues: {msg}")
            return False, msg


# ----------------------------------------------------------------------
# Workspace-wide helpers (shared by scripts that support project_code=all)
# ----------------------------------------------------------------------

def list_workspace_project_codes(
    api_token: str,
    base_url: Optional[str] = None,
    quiet: bool = True,
) -> List[str]:
    """
    Return every project code in the workspace associated with `api_token`.

    `project_code` on the probe client is irrelevant because /project is a
    workspace-level endpoint — we just need a valid `QaseAPI` instance.
    """
    probe = QaseAPI(api_token, "_probe", base_url)
    projects = probe.get_all_projects(quiet=quiet)
    codes: List[str] = []
    for p in projects:
        c = p.get("code")
        if c:
            codes.append(str(c))
    return codes


def confirm_run_all_projects(
    codes: List[str],
    action: str = "run this script against",
    dry_run: bool = False,
) -> bool:
    """
    Print the project codes and ask the user to confirm a workspace-wide
    run. Returns True on a literal 'yes' answer, False otherwise.

    In dry-run mode the list is still printed, but the prompt is skipped
    (nothing is being written, so there is nothing to confirm).
    Non-interactive terminals (no TTY) are treated as a rejection.
    """
    print(f"\nFound {len(codes)} project(s) in this workspace:")
    for c in codes:
        print(f"  - {c}")
    print()

    if dry_run:
        print("[DRY RUN] Skipping confirmation — no changes will be made.")
        return True

    if not sys.stdin.isatty():
        print(
            "Non-interactive terminal detected — refusing to run against "
            "all projects without explicit confirmation. Re-run in an "
            "interactive shell."
        )
        return False

    prompt = (
        f"You are about to {action} ALL {len(codes)} project(s) listed "
        f"above. Type 'yes' to continue, anything else to abort: "
    )
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return False
    return answer == "yes"