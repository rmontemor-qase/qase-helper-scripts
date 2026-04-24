#!/usr/bin/env python3
"""
Qase Migration Script: Link JIRA Issues to Test Cases

This script:
1. Fetches all test cases from a Qase project (or all projects when project_code is "all")
2. Extracts JIRA issue IDs from the refs field in test cases
3. Attaches JIRA issues to test cases using the Qase External Issues API
"""

import json
import os
import sys
import argparse
import re
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Tuple

from qase_api import QaseAPI, resolve_qase_base_url

JIRA_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def extract_jira_project_keys_from_text(text: Optional[str]) -> Set[str]:
    """Extract JIRA project keys (prefix before '-') from issue keys in error/API text."""
    if not text:
        return set()
    keys: Set[str] = set()
    for m in JIRA_ISSUE_KEY_RE.finditer(text):
        part = m.group(1).split("-", 1)[0]
        if part:
            keys.add(part)
    return keys


class RateLimiter:
    """Global spacing for API calls (~calls_per_minute, default 1000/min)."""

    def __init__(self, calls_per_minute: int = 1000):
        self._min_interval = 60.0 / max(1, calls_per_minute)
        self._lock = threading.Lock()
        self._next_at = time.monotonic()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                time.sleep(self._next_at - now)
                now = time.monotonic()
            self._next_at = now + self._min_interval


class ProgressState:
    """Thread-safe progress line (stdout): bar + processed/total + attached + errors."""

    def __init__(self, total: int, width: int = 40):
        self.total = max(1, total)
        self.processed = 0
        self.attached = 0
        self.errors = 0
        self._lock = threading.Lock()
        self._width = width

    def set_total(self, total: int) -> None:
        with self._lock:
            self.total = max(1, total)
            self._render()

    def add_processed(self, n: int = 1) -> None:
        with self._lock:
            self.processed += n
            self._render()

    def add_attached(self, n: int = 1) -> None:
        with self._lock:
            self.attached += n
            self._render()

    def add_errors(self, n: int = 1) -> None:
        with self._lock:
            self.errors += n
            self._render()

    def _render(self) -> None:
        t = self.total
        p = min(self.processed, t)
        pct = 100.0 * p / t
        w = self._width
        filled = int(w * p / t) if t else w
        filled = min(filled, w)
        bar = "=" * filled + (">" if filled < w else "")
        bar = bar.ljust(w, "-")[:w]
        line = (
            f"\r[{bar}] {pct:5.1f}% {p}/{t} | attached: {self.attached} | errors: {self.errors}   "
        )
        sys.stdout.write(line)
        sys.stdout.flush()

    def done(self) -> None:
        with self._lock:
            self._render()
        sys.stdout.write("\n")
        sys.stdout.flush()


def setup_file_logging(log_path: str, verbose: bool = False) -> logging.Logger:
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    logger = logging.getLogger("link_jira_issues")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
    logger.propagate = False
    return logger


def resolve_refs_field_id(
    api: QaseAPI,
    refs_field_name: str,
    refs_field_id: Optional[int],
    log: logging.Logger,
    rate_limiter: Optional[RateLimiter] = None,
) -> Optional[int]:
    if refs_field_id is not None:
        log.info("Using provided refs field ID: %s", refs_field_id)
        return refs_field_id

    log.info("Resolving refs field '%s' from custom fields...", refs_field_name)
    custom_fields = api.get_custom_fields(quiet=True, rate_limiter=rate_limiter)
    if not custom_fields:
        log.warning("No custom fields found; will use system refs/references only.")
        return None

    search_names = [refs_field_name, "references", "refs"]
    for field in custom_fields:
        title = field.get("title", "")
        field_id = field.get("id")
        if not title or not field_id:
            continue
        for search_name in search_names:
            if title == search_name or title.lower() == search_name.lower():
                log.info("Matched custom field '%s' (ID %s)", title, field_id)
                return int(field_id)

    log.warning("Custom field '%s' not found by name; using system refs/references.", refs_field_name)
    return None


class JIRAIssueExtractor:
    """Handles extraction of JIRA issue IDs from test case fields."""

    @staticmethod
    def _extract_jira_issue_ids(text: Optional[str]) -> List[str]:
        if not text:
            return []
        jira_pattern = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
        matches = jira_pattern.findall(text)
        seen = set()
        unique_ids = []
        for jira_id in matches:
            if jira_id not in seen:
                seen.add(jira_id)
                unique_ids.append(jira_id)
        return unique_ids

    @staticmethod
    def extract_from_test_case(
        test_case: Dict[str, Any],
        refs_field_id: Optional[int] = None,
        debug: bool = False,
    ) -> List[str]:
        refs = None
        if refs_field_id is not None:
            for field in test_case.get("custom_fields", []):
                if field.get("id") == refs_field_id:
                    refs = field.get("value")
                    break
        if not refs:
            refs = test_case.get("refs") or test_case.get("references")
        if not refs:
            return []

        if isinstance(refs, list):
            refs_list = refs
        elif isinstance(refs, str):
            refs_list = [refs]
        else:
            return []

        jira_ids = []
        for ref in refs_list:
            if isinstance(ref, str):
                jira_ids.extend(JIRAIssueExtractor._extract_jira_issue_ids(ref))

        seen = set()
        unique_ids = []
        for jira_id in jira_ids:
            if jira_id not in seen:
                seen.add(jira_id)
                unique_ids.append(jira_id)
        return unique_ids


class QaseJIRALinker:
    """Main class for linking JIRA issues to Qase test cases (single project_code)."""

    def __init__(
        self,
        api_token: str,
        project_code: str,
        external_issue_type: str = "jira-cloud",
        batch_size: int = 50,
        refs_field_name: str = "refs",
        refs_field_id: Optional[int] = None,
        base_url: Optional[str] = None,
    ):
        self.api = QaseAPI(api_token, project_code, base_url)
        self.extractor = JIRAIssueExtractor()
        self.external_issue_type = external_issue_type
        self.batch_size = batch_size
        self.refs_field_name = refs_field_name
        self.refs_field_id = refs_field_id

    def process_all_cases(
        self,
        dry_run: bool = False,
        verbose: bool = False,
        progress: Optional[ProgressState] = None,
        rate_limiter: Optional[RateLimiter] = None,
        jira_failed_projects: Optional[Set[str]] = None,
        fail_lock: Optional[threading.Lock] = None,
        file_log: Optional[logging.Logger] = None,
        sync_progress_total: bool = True,
    ) -> Dict[str, Any]:
        log = file_log or logging.getLogger("link_jira_issues")
        rl = rate_limiter or RateLimiter()
        jfp = jira_failed_projects if jira_failed_projects is not None else set()
        fl = fail_lock or threading.Lock()

        self.refs_field_id = resolve_refs_field_id(
            self.api, self.refs_field_name, self.refs_field_id, log, rate_limiter=rl
        )

        test_cases = self.api.get_all_test_cases(quiet=True, rate_limiter=rl)
        if sync_progress_total and progress and len(test_cases) != progress.total:
            progress.set_total(len(test_cases))
        stats: Dict[str, Any] = {
            "total": len(test_cases),
            "with_jira_issues": 0,
            "total_jira_issues": 0,
            "unique_jira_issues": set(),
            "cases_attached": 0,
            "batches_attached": 0,
            "errors": 0,
            "cases_with_refs": 0,
            "cases_without_refs": 0,
        }

        jira_links: List[Dict[str, Any]] = []

        for test_case in test_cases:
            case_id = test_case.get("id")
            refs_found = False
            if self.refs_field_id is not None:
                for field in test_case.get("custom_fields", []):
                    if field.get("id") == self.refs_field_id:
                        refs_found = True
                        break
            if not refs_found:
                refs_found = bool(test_case.get("refs") or test_case.get("references"))

            if refs_found:
                stats["cases_with_refs"] += 1
            else:
                stats["cases_without_refs"] += 1

            jira_ids = self.extractor.extract_from_test_case(
                test_case, self.refs_field_id, debug=verbose
            )
            if not jira_ids:
                if progress:
                    progress.add_processed(1)
                continue

            stats["with_jira_issues"] += 1
            stats["total_jira_issues"] += len(jira_ids)
            stats["unique_jira_issues"].update(jira_ids)
            jira_links.append({"case_id": case_id, "external_issues": jira_ids})

        if not jira_links:
            log.info("Project %s: no JIRA issues to attach.", self.api.project_code)
            return stats

        if dry_run:
            log.info(
                "Project %s: DRY RUN — would attach for %s cases with issues.",
                self.api.project_code,
                len(jira_links),
            )
            if progress:
                progress.add_processed(len(jira_links))
            return stats

        failed_batches: List[Tuple[int, List[Dict[str, Any]]]] = []

        for i in range(0, len(jira_links), self.batch_size):
            batch = jira_links[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            rl.acquire()
            ok, err = self.api.attach_external_issues_with_error(
                self.external_issue_type, batch, quiet=True
            )
            if ok:
                stats["cases_attached"] += len(batch)
                stats["batches_attached"] += 1
                if progress:
                    progress.add_attached(len(batch))
                    progress.add_processed(len(batch))
            else:
                failed_batches.append((batch_num, batch))
                with fl:
                    jfp.update(extract_jira_project_keys_from_text(err or ""))
                log.warning(
                    "Batch %s failed project=%s: %s",
                    batch_num,
                    self.api.project_code,
                    err,
                )

        for batch_num, batch in failed_batches:
            log.info(
                "Retrying batch %s as single-case attaches (%s cases)...",
                batch_num,
                len(batch),
            )
            for link in batch:
                rl.acquire()
                ok, err = self.api.attach_external_issues_with_error(
                    self.external_issue_type, [link], quiet=True
                )
                if ok:
                    stats["cases_attached"] += 1
                    if progress:
                        progress.add_attached(1)
                        progress.add_processed(1)
                else:
                    stats["errors"] += 1
                    if progress:
                        progress.add_errors(1)
                        progress.add_processed(1)
                    with fl:
                        jfp.update(extract_jira_project_keys_from_text(err or ""))
                    log.warning(
                        "Case %s failed project=%s: %s",
                        link.get("case_id"),
                        self.api.project_code,
                        err,
                    )

        return stats


def _fetch_project_codes(
    api: QaseAPI, log: logging.Logger, rate_limiter: Optional[RateLimiter] = None
) -> List[str]:
    projects = api.get_all_projects(quiet=True, rate_limiter=rate_limiter)
    codes = []
    for p in projects:
        c = p.get("code")
        if c:
            codes.append(str(c))
    log.info("Discovered %s project(s).", len(codes))
    return codes


def _fetch_case_totals_parallel(
    api_token: str,
    base_url: str,
    project_codes: List[str],
    workers: int,
    rate_limiter: RateLimiter,
    log: logging.Logger,
) -> Dict[str, int]:
    totals: Dict[str, int] = {}

    def one(code: str) -> Tuple[str, int]:
        api = QaseAPI(api_token, code, base_url)
        return code, api.get_test_case_total(quiet=True, rate_limiter=rate_limiter)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(one, c): c for c in project_codes}
        for fut in as_completed(futs):
            code, t = fut.result()
            totals[code] = t
            log.debug("Case total for %s: %s", code, t)
    return totals


def run_all_projects(
    api_token: str,
    base_url: str,
    external_issue_type: str,
    batch_size: int,
    refs_field_name: str,
    refs_field_id: Optional[int],
    dry_run: bool,
    verbose: bool,
    parallel_workers: int,
    calls_per_minute: int,
    log_path: str,
) -> None:
    log = setup_file_logging(log_path, verbose=verbose)
    abs_log = os.path.abspath(log_path)
    print(f"Log file: {abs_log}", file=sys.stderr)
    log.info("Starting workspace run (all projects). Log file: %s", abs_log)

    rate_limiter = RateLimiter(calls_per_minute=calls_per_minute)
    probe = QaseAPI(api_token, "DUMMY", base_url)
    codes = _fetch_project_codes(probe, log, rate_limiter=rate_limiter)
    if not codes:
        log.error("No projects returned from API.")
        return
    totals_map = _fetch_case_totals_parallel(
        api_token, base_url, codes, parallel_workers, rate_limiter, log
    )
    global_total = sum(totals_map.values())
    log.info("Total test cases (sum across projects): %s", global_total)

    first_api = QaseAPI(api_token, codes[0], base_url)
    resolved_refs_id = resolve_refs_field_id(
        first_api, refs_field_name, refs_field_id, log, rate_limiter=rate_limiter
    )

    jira_failed: Set[str] = set()
    fail_lock = threading.Lock()
    progress = ProgressState(global_total)

    def worker(project_code: str) -> Dict[str, Any]:
        linker = QaseJIRALinker(
            api_token=api_token,
            project_code=project_code,
            external_issue_type=external_issue_type,
            batch_size=batch_size,
            refs_field_name=refs_field_name,
            refs_field_id=resolved_refs_id,
            base_url=base_url,
        )
        return linker.process_all_cases(
            dry_run=dry_run,
            verbose=verbose,
            progress=progress,
            rate_limiter=rate_limiter,
            jira_failed_projects=jira_failed,
            fail_lock=fail_lock,
            file_log=log,
            sync_progress_total=False,
        )

    aggregate: Dict[str, Any] = {
        "total": 0,
        "cases_attached": 0,
        "errors": 0,
        "with_jira_issues": 0,
    }

    with ThreadPoolExecutor(max_workers=max(1, parallel_workers)) as ex:
        futures = {ex.submit(worker, c): c for c in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                st = fut.result()
            except Exception as e:
                log.exception("Project %s failed: %s", code, e)
                continue
            aggregate["total"] += st.get("total", 0)
            aggregate["cases_attached"] += st.get("cases_attached", 0)
            aggregate["errors"] += st.get("errors", 0)
            aggregate["with_jira_issues"] += st.get("with_jira_issues", 0)

    progress.done()
    log.info("Finished. Attached: %s, errors: %s", aggregate["cases_attached"], aggregate["errors"])
    log.info(
        "JIRA project keys with not-found issues (for customer): %s",
        ", ".join(sorted(jira_failed)) if jira_failed else "(none)",
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n--- JIRA project keys (not found in Jira integration) ---\n")
        f.write(json.dumps(sorted(jira_failed), indent=2))
        f.write("\n")


def run_single_project(
    api_token: str,
    project_code: str,
    base_url: str,
    external_issue_type: str,
    batch_size: int,
    refs_field_name: str,
    refs_field_id: Optional[int],
    dry_run: bool,
    verbose: bool,
    calls_per_minute: int,
    log_path: str,
) -> None:
    log = setup_file_logging(log_path, verbose=verbose)
    abs_log = os.path.abspath(log_path)
    print(f"Log file: {abs_log}", file=sys.stderr)
    log.info("Starting single-project run. Log: %s", abs_log)

    rate_limiter = RateLimiter(calls_per_minute=calls_per_minute)
    api = QaseAPI(api_token, project_code, base_url)
    total_cases = api.get_test_case_total(quiet=True, rate_limiter=rate_limiter)

    jira_failed: Set[str] = set()
    progress = ProgressState(total_cases)

    linker = QaseJIRALinker(
        api_token=api_token,
        project_code=project_code,
        external_issue_type=external_issue_type,
        batch_size=batch_size,
        refs_field_name=refs_field_name,
        refs_field_id=refs_field_id,
        base_url=base_url,
    )
    linker.process_all_cases(
        dry_run=dry_run,
        verbose=verbose,
        progress=progress,
        rate_limiter=rate_limiter,
        jira_failed_projects=jira_failed,
        fail_lock=threading.Lock(),
        file_log=log,
    )
    progress.done()
    log.info(
        "JIRA project keys with not-found issues (for customer): %s",
        ", ".join(sorted(jira_failed)) if jira_failed else "(none)",
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n--- JIRA project keys (not found in Jira integration) ---\n")
        f.write(json.dumps(sorted(jira_failed), indent=2))
        f.write("\n")


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Config file '{config_path}' not found. "
            f"Please create it with 'api_token' and 'project_code' fields."
        )
    with open(config_path, "r") as f:
        return json.load(f)


def _default_log_path() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join("logs", f"link_jira_{ts}.log")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Link JIRA issues to Qase test cases by extracting JIRA IDs from test case fields"
    )
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument("--token", help="Qase API token (overrides config file)")
    parser.add_argument("--project", help="Qase project code (overrides config); use 'all' for every project")
    parser.add_argument("--host", help="Qase API host (overrides config 'host')")
    parser.add_argument(
        "--type",
        choices=["jira-cloud", "jira-server"],
        default="jira-cloud",
        help="Type of JIRA instance (default: jira-cloud)",
    )
    parser.add_argument("--batch-size", type=int, default=50, help="Cases per attach batch (default: 50)")
    parser.add_argument(
        "--refs-field",
        default=None,
        help="Refs field name (default: config or 'refs')",
    )
    parser.add_argument("--refs-field-id", type=int, help="Refs custom field ID (skips name lookup)")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only; no attach requests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose file log (not stdout)")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Parallel workers for multi-project attach (default: config or 8)",
    )
    parser.add_argument(
        "--calls-per-minute",
        type=int,
        default=None,
        help="Global API rate limit spacing (default: config or 1000)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Log file path (default: logs/link_jira_<timestamp>.log)",
    )

    args = parser.parse_args()

    api_token = args.token
    project_code = args.project
    refs_field_name = args.refs_field
    refs_field_id = args.refs_field_id
    config: Optional[Dict[str, Any]] = None

    try:
        config = load_config(args.config)
        api_token = api_token or config.get("api_token")
        project_code = project_code or config.get("project_code")
        if not refs_field_name:
            refs_field_name = config.get("jira_refs_field") or "refs"
        if not refs_field_id:
            rfi = config.get("jira_refs_field_id")
            if rfi is not None:
                try:
                    refs_field_id = int(rfi)
                except (TypeError, ValueError):
                    refs_field_id = None
    except (FileNotFoundError, ValueError) as e:
        if not api_token or not project_code:
            parser.error(
                f"Either provide --token and --project arguments, or create a valid config file. Error: {e}"
            )

    if not api_token:
        parser.error("API token is required (provide via --token or config file)")
    if not project_code:
        parser.error("Project code is required (provide via --project or config file)")

    base_url = resolve_qase_base_url(args.host, config, args.config)

    workers = args.workers
    if workers is None and config:
        workers = config.get("parallel_workers")
    if workers is None:
        workers = 8

    rpm = args.calls_per_minute
    if rpm is None and config:
        rpm = config.get("calls_per_minute")
    if rpm is None:
        rpm = 1000

    log_path = args.log_file
    if not log_path and config and config.get("log_file"):
        log_path = config["log_file"]
    if not log_path:
        log_path = _default_log_path()

    pc = str(project_code).strip().lower()
    if pc == "all":
        run_all_projects(
            api_token=api_token,
            base_url=base_url,
            external_issue_type=args.type,
            batch_size=args.batch_size,
            refs_field_name=refs_field_name or "refs",
            refs_field_id=refs_field_id,
            dry_run=args.dry_run,
            verbose=args.verbose,
            parallel_workers=workers,
            calls_per_minute=rpm,
            log_path=log_path,
        )
    else:
        run_single_project(
            api_token=api_token,
            project_code=str(project_code).strip(),
            base_url=base_url,
            external_issue_type=args.type,
            batch_size=args.batch_size,
            refs_field_name=refs_field_name or "refs",
            refs_field_id=refs_field_id,
            dry_run=args.dry_run,
            verbose=args.verbose,
            calls_per_minute=rpm,
            log_path=log_path,
        )


if __name__ == "__main__":
    main()
