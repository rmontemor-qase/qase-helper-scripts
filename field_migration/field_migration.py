#!/usr/bin/env python3
"""
Qase Field Migration Script

Copies the value of one field on every test case in a Qase project into
another field. Both sides can be either a **system** field (e.g.
`preconditions`, `description`, `postconditions`) or a **custom** field;
any combination is supported:

    system  -> custom
    custom  -> system
    system  -> system
    custom  -> custom

By default the source field is left untouched after the copy. Pass
`clear_source: true` in `config.json` (or `--clear-source` on the CLI)
to also blank out the source on every migrated case.
"""

import json
import os
import sys
import argparse
from typing import Dict, List, Optional, Tuple, Any, Literal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qase_api import (
    QaseAPI,
    resolve_qase_base_url,
    list_workspace_project_codes,
    confirm_run_all_projects,
)


FieldKind = Literal["system", "custom"]
# Resolved field reference: ('system', <slug>) or ('custom', <int id>)
FieldRef = Tuple[FieldKind, Any]


class QaseFieldMigration:
    """Copy field content from one field to another on every test case."""

    def __init__(
        self,
        api_token: str,
        project_code: str,
        source_field_name: str,
        destination_field_name: str,
        destination_field_id: Optional[int] = None,
        clear_source: bool = False,
        base_url: Optional[str] = None,
        source_kind_hint: Optional[FieldKind] = None,
        destination_kind_hint: Optional[FieldKind] = None,
    ):
        """
        Args:
            api_token: Qase API token.
            project_code: Project code (e.g., 'DEMO').
            source_field_name: Name (title or slug) of the source field.
            destination_field_name: Name (title) of the destination field.
            destination_field_id: Optional explicit *custom* field ID for the
                destination. If provided, the destination is treated as a
                custom field with this ID and no name lookup is done.
            clear_source: If True, the source field is cleared after copy.
                Defaults to False.
            base_url: Qase API base URL.
            source_kind_hint / destination_kind_hint: When set to
                'system' or 'custom', the resolver silently picks that
                kind if the name matches both a system and a custom
                field — no ambiguity prompt. Used by the workspace-wide
                ('all' projects) loop to reuse the first project's
                disambiguation decision for every subsequent project.
        """
        self.api = QaseAPI(api_token, project_code, base_url)
        self.source_field_name = source_field_name
        self.destination_field_name = destination_field_name
        self.destination_field_id_override = destination_field_id
        self.clear_source = clear_source
        self._src_kind_hint = source_kind_hint
        self._dest_kind_hint = destination_kind_hint

        self._src_ref: Optional[FieldRef] = None
        self._dest_ref: Optional[FieldRef] = None

    # ------------------------------------------------------------------
    # Field resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _match_system_fields(name: str, system_fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return system fields whose title or slug matches `name` (case-insensitive)."""
        n = name.lower()
        matches = []
        for f in system_fields:
            title = (f.get("title") or "").lower()
            slug = (f.get("slug") or "").lower()
            if title == n or slug == n:
                matches.append(f)
        return matches

    @staticmethod
    def _match_custom_fields(name: str, custom_fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return custom fields whose title matches `name` (case-insensitive)."""
        n = name.lower()
        return [f for f in custom_fields if (f.get("title") or "").lower() == n]

    def _resolve_field(
        self,
        name: str,
        role: str,
        system_fields: List[Dict[str, Any]],
        custom_fields: List[Dict[str, Any]],
        kind_hint: Optional[FieldKind] = None,
    ) -> Optional[FieldRef]:
        """
        Look up `name` across system and custom fields and return a single
        `(kind, key)` reference. If the name matches more than one field,
        prompt the user interactively to choose — unless `kind_hint` is
        set, in which case the matching hint kind is chosen silently.
        """
        sys_matches = self._match_system_fields(name, system_fields)
        cus_matches = self._match_custom_fields(name, custom_fields)
        total = len(sys_matches) + len(cus_matches)

        if total == 0:
            return None

        if total == 1:
            if sys_matches:
                slug = sys_matches[0].get("slug")
                print(f"Resolved {role} field '{name}' to system field (slug: {slug}).")
                return ("system", slug)
            cf = cus_matches[0]
            cid = int(cf.get("id"))
            print(f"Resolved {role} field '{name}' to custom field (id: {cid}).")
            return ("custom", cid)

        # Ambiguous — try kind hint first
        if kind_hint == "system" and sys_matches:
            slug = sys_matches[0].get("slug")
            print(
                f"Resolved {role} field '{name}' to system field (slug: {slug}) "
                f"using remembered choice from earlier project."
            )
            return ("system", slug)
        if kind_hint == "custom" and cus_matches:
            cf = cus_matches[0]
            cid = int(cf.get("id"))
            print(
                f"Resolved {role} field '{name}' to custom field (id: {cid}) "
                f"using remembered choice from earlier project."
            )
            return ("custom", cid)

        return self._disambiguate(name, role, sys_matches, cus_matches)

    @staticmethod
    def _disambiguate(
        name: str,
        role: str,
        sys_matches: List[Dict[str, Any]],
        cus_matches: List[Dict[str, Any]],
    ) -> FieldRef:
        """
        Multiple fields match `name`. Ask the user which one to use.
        The user is expected to type the slug (for a system field) or the
        numeric id (for a custom field) from the list we print.
        """
        if not sys.stdin.isatty():
            raise RuntimeError(
                f"The {role} field name '{name}' is ambiguous "
                f"({len(sys_matches)} system + {len(cus_matches)} custom). "
                f"The script needs an interactive TTY to resolve this. "
                f"Either rename one of the fields, or pass an explicit "
                f"--destination-field-id (for destination) / use a more "
                f"specific name."
            )

        print()
        print(f"The {role} field name '{name}' matches more than one field:")
        valid_keys: Dict[str, FieldRef] = {}
        for f in sys_matches:
            slug = f.get("slug")
            title = f.get("title")
            print(f"  [{slug}]  system field  title='{title}'  slug='{slug}'")
            if slug:
                valid_keys[str(slug).lower()] = ("system", slug)
        for f in cus_matches:
            cid = f.get("id")
            title = f.get("title")
            print(f"  [{cid}]  custom field  title='{title}'  id={cid}")
            if cid is not None:
                valid_keys[str(cid)] = ("custom", int(cid))

        while True:
            answer = input(
                f"Enter the slug (for a system field) or id (for a custom field) to use as {role}: "
            ).strip()
            if not answer:
                continue
            key = answer.lower()
            if key in valid_keys:
                chosen = valid_keys[key]
                print(f"Using {chosen[0]} field ({chosen[1]}) as {role}.")
                return chosen
            print(f"'{answer}' is not one of the listed options. Try again.")

    # ------------------------------------------------------------------
    # Per-case logic
    # ------------------------------------------------------------------

    @staticmethod
    def _read_field_value(test_case: Dict[str, Any], ref: FieldRef) -> str:
        """Return the current string value of a field on a test case."""
        kind, key = ref
        if kind == "system":
            return test_case.get(key, "") or ""
        for cf in test_case.get("custom_fields", []) or []:
            if cf.get("id") == key:
                return cf.get("value") or ""
        return ""

    def analyze_test_case(self, test_case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Return the PATCH body needed to migrate this case, or None if there
        is nothing to do.
        """
        assert self._src_ref is not None and self._dest_ref is not None

        source_value = self._read_field_value(test_case, self._src_ref)
        if not source_value or not source_value.strip():
            return None

        updates: Dict[str, Any] = {}
        custom: Dict[str, Any] = {}

        # Write destination
        dest_kind, dest_key = self._dest_ref
        if dest_kind == "system":
            updates[dest_key] = source_value
        else:
            custom[str(dest_key)] = source_value

        # Optionally clear source
        if self.clear_source:
            src_kind, src_key = self._src_ref
            if src_kind == "system":
                updates[src_key] = ""
            else:
                custom[str(src_key)] = ""

        if custom:
            updates["custom_field"] = custom

        return updates

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    @staticmethod
    def display_progress_bar(current: int, total: int, stats: Dict[str, int], bar_length: int = 40):
        if total == 0:
            return
        percent = (current / total) * 100
        filled_length = int(bar_length * current // total)
        bar = '=' * filled_length + '>' + '-' * (bar_length - filled_length - 1)
        stats_str = (
            f"Needs migration: {stats['needs_migration']}, "
            f"Migrated: {stats['migrated']}, "
            f"Errors: {stats['errors']}, "
            f"Skipped: {stats['skipped']}"
        )
        print(f'\rProgress: [{bar}] {percent:.1f}% ({current}/{total}) | {stats_str}', end='', flush=True)
        if current == total:
            print()

    def _resolve_fields(self) -> bool:
        """Resolve source and destination field refs. Return False on failure."""
        print("Fetching system and custom field definitions...")
        system_fields = self.api.get_system_fields()
        custom_fields = self.api.get_custom_fields()

        # Source
        self._src_ref = self._resolve_field(
            self.source_field_name, "source", system_fields, custom_fields,
            kind_hint=self._src_kind_hint,
        )
        if self._src_ref is None:
            print(
                f"Error: source field '{self.source_field_name}' was not found "
                f"as a system field or as a custom field."
            )
            return False

        # Destination — explicit custom ID override wins
        if self.destination_field_id_override is not None:
            self._dest_ref = ("custom", int(self.destination_field_id_override))
            print(
                f"Using destination custom field id from config/CLI: "
                f"{self.destination_field_id_override} (name: '{self.destination_field_name}')"
            )
        else:
            self._dest_ref = self._resolve_field(
                self.destination_field_name, "destination", system_fields, custom_fields,
                kind_hint=self._dest_kind_hint,
            )
            if self._dest_ref is None:
                print(
                    f"Error: destination field '{self.destination_field_name}' was not "
                    f"found as a system field or as a custom field."
                )
                return False

        if self._src_ref == self._dest_ref:
            print(
                "Error: source and destination resolve to the same field "
                f"({self._src_ref[0]}: {self._src_ref[1]}). Nothing to do."
            )
            return False

        return True

    def process_all_cases(self, dry_run: bool = False, verbose: bool = False) -> Dict[str, int]:
        if not self._resolve_fields():
            return {"total": 0, "needs_migration": 0, "migrated": 0, "errors": 0, "skipped": 0}

        src_kind, src_key = self._src_ref  # type: ignore[misc]
        dest_kind, dest_key = self._dest_ref  # type: ignore[misc]

        test_cases = self.api.get_all_test_cases()
        stats = {
            "total": len(test_cases),
            "needs_migration": 0,
            "migrated": 0,
            "errors": 0,
            "skipped": 0,
        }

        print(f"\nAnalyzing {stats['total']} test cases...")
        print(
            f"Migrating from {src_kind} '{self.source_field_name}' ({src_key}) "
            f"to {dest_kind} '{self.destination_field_name}' ({dest_key})"
        )
        print(f"clear_source = {self.clear_source}")
        print()

        processed_count = 0
        for test_case in test_cases:
            processed_count += 1
            case_id = test_case.get("id")
            title = test_case.get("title", "Untitled")
            source_value = self._read_field_value(test_case, self._src_ref)  # type: ignore[arg-type]

            if verbose:
                if processed_count == 1 or processed_count % 10 == 0 or processed_count == stats['total']:
                    self.display_progress_bar(processed_count, stats['total'], stats)
            else:
                self.display_progress_bar(processed_count, stats['total'], stats)

            if verbose:
                has_source = bool(source_value and source_value.strip())
                dest_value = self._read_field_value(test_case, self._dest_ref)  # type: ignore[arg-type]
                print(
                    f"\nCase {case_id} ('{title}'): "
                    f"{self.source_field_name}={'yes' if has_source else 'no'}, "
                    f"{self.destination_field_name}={'set' if dest_value else 'empty'}"
                )

            updates = self.analyze_test_case(test_case)
            if updates:
                stats["needs_migration"] += 1
                if verbose:
                    print(f"\nCase {case_id} ('{title}') needs migration:")
                    snippet = source_value[:100] + ('...' if len(source_value) > 100 else '')
                    print(f"  {self.source_field_name} value: {snippet}")

                if not dry_run:
                    if self.api.update_test_case(case_id, updates):
                        stats["migrated"] += 1
                        if verbose:
                            clear_txt = f" and cleared {self.source_field_name}" if self.clear_source else ""
                            print(f"  ✓ Case {case_id} migrated{clear_txt}")
                    else:
                        stats["errors"] += 1
                        print(f"\n  ✗ Failed to migrate case {case_id}")
                else:
                    if verbose:
                        print(f"  [DRY RUN] Would:")
                        print(
                            f"    - Write to {dest_kind} field "
                            f"'{self.destination_field_name}' ({dest_key})"
                        )
                        if self.clear_source:
                            print(
                                f"    - Clear {src_kind} field "
                                f"'{self.source_field_name}' ({src_key})"
                            )
                    stats["migrated"] += 1  # "would-be migrated" in dry run
            else:
                if verbose and not (source_value and source_value.strip()):
                    print(f"\nCase {case_id} ('{title}'): source is empty, skipping")

        self.display_progress_bar(processed_count, stats['total'], stats)
        return stats

    def run(self, dry_run: bool = False, verbose: bool = False) -> Dict[str, int]:
        print("=" * 60)
        print(f"Qase Field Migration — project: {self.api.project_code}")
        print("=" * 60)
        print(f"Source field:      {self.source_field_name}")
        print(f"Destination field: {self.destination_field_name}")
        print(f"Clear source:      {self.clear_source}")
        if dry_run:
            print("DRY RUN MODE - No changes will be made")
        if verbose:
            print("VERBOSE MODE - Showing detailed analysis")
        print()

        stats = self.process_all_cases(dry_run=dry_run, verbose=verbose)

        print("\n" + "-" * 60)
        print(f"Summary for project {self.api.project_code}:")
        print(f"  Total test cases:         {stats['total']}")
        print(f"  Cases needing migration:  {stats['needs_migration']}")
        print(f"  Cases migrated:           {stats['migrated']}")
        print(f"  Cases skipped:            {stats['skipped']}")
        print(f"  Errors:                   {stats['errors']}")
        if stats['needs_migration'] == 0 and stats['total'] > 0:
            print(f"  [INFO] No test cases had a non-empty '{self.source_field_name}' to migrate.")
        return stats


# ----------------------------------------------------------------------
# Config + CLI
# ----------------------------------------------------------------------

def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Config file '{config_path}' not found. "
            f"Please create it with 'api_token' and 'project_code' fields."
        )
    with open(config_path, 'r') as f:
        config = json.load(f)
    if "api_token" not in config:
        raise ValueError("Config file must contain 'api_token' field")
    if "project_code" not in config:
        raise ValueError("Config file must contain 'project_code' field")
    return config


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Migrate field content between any two fields (system or custom) "
            "on every test case of a Qase project."
        )
    )
    parser.add_argument("--config", default="config.json", help="Path to config file (default: config.json)")
    parser.add_argument("--token", help="Qase API token (overrides config)")
    parser.add_argument("--project", help="Qase project code (overrides config)")
    parser.add_argument("--host", help="Qase API host (overrides config 'host')")
    parser.add_argument(
        "--source-field",
        help=(
            "Name of the source field. Can be a system field name/slug "
            "(e.g. 'preconditions') or a custom field title."
        ),
    )
    parser.add_argument(
        "--destination-field",
        help=(
            "Name of the destination field. Can be a system field name/slug "
            "or a custom field title."
        ),
    )
    parser.add_argument(
        "--destination-field-id",
        type=int,
        help=(
            "Destination *custom* field ID. If set, the destination is forced "
            "to this custom field and name lookup is skipped."
        ),
    )

    clear_group = parser.add_mutually_exclusive_group()
    clear_group.add_argument(
        "--clear-source",
        dest="clear_source",
        action="store_true",
        default=None,
        help="After copying, blank out the source field on each migrated case.",
    )
    clear_group.add_argument(
        "--no-clear-source",
        dest="clear_source",
        action="store_false",
        default=None,
        help="Leave the source field untouched after copying (default).",
    )

    parser.add_argument("--dry-run", action="store_true", help="Analyze only; no API writes.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print details for every test case.")

    args = parser.parse_args()

    api_token = args.token
    project_code = args.project
    source_field = args.source_field
    destination_field = args.destination_field
    destination_field_id = args.destination_field_id
    clear_source = args.clear_source  # tri-state: True/False/None
    config: Optional[Dict[str, Any]] = None

    try:
        config = load_config(args.config)
        api_token = api_token or config.get("api_token")
        project_code = project_code or config.get("project_code")
        source_field = source_field or config.get("source_field")
        destination_field = destination_field or config.get("destination_field")
        if destination_field_id is None and "destination_field_id" in config:
            v = config.get("destination_field_id")
            if v is not None:
                try:
                    destination_field_id = int(v)
                except (ValueError, TypeError):
                    destination_field_id = None
        if clear_source is None:
            clear_source = bool(config.get("clear_source", False))
    except (FileNotFoundError, ValueError) as e:
        if not api_token or not project_code:
            parser.error(
                f"Either provide --token and --project arguments, "
                f"or create a valid config file. Error: {e}"
            )

    if clear_source is None:
        clear_source = False

    if not api_token:
        parser.error("API token is required (provide via --token or config file)")
    if not project_code:
        parser.error("Project code is required (provide via --project or config file)")
    if not source_field:
        parser.error("Source field name is required (provide via --source-field or set 'source_field' in config.json)")
    if not destination_field:
        parser.error("Destination field name is required (provide via --destination-field or set 'destination_field' in config.json)")

    base_url = resolve_qase_base_url(args.host, config, args.config)

    if str(project_code).strip().lower() == "all":
        if destination_field_id is not None:
            print(
                "[WARN] 'destination_field_id' is project-specific and is "
                "ignored when project_code='all'. Field names will be "
                "resolved per project."
            )
            destination_field_id = None

        codes = list_workspace_project_codes(api_token, base_url)
        if not codes:
            parser.error("No projects returned by the API.")
        action = (
            f"migrate '{source_field}' to '{destination_field}'"
            + (" (and clear source)" if clear_source else "")
            + " on test cases in"
        )
        if not confirm_run_all_projects(codes, action=action, dry_run=args.dry_run):
            print("Aborted.")
            return

        totals = {"total": 0, "needs_migration": 0, "migrated": 0, "errors": 0, "skipped": 0}
        src_hint: Optional[FieldKind] = None
        dest_hint: Optional[FieldKind] = None

        for code in codes:
            migration = QaseFieldMigration(
                api_token=api_token,
                project_code=code,
                source_field_name=source_field,
                destination_field_name=destination_field,
                destination_field_id=None,
                clear_source=clear_source,
                base_url=base_url,
                source_kind_hint=src_hint,
                destination_kind_hint=dest_hint,
            )
            stats = migration.run(dry_run=args.dry_run, verbose=args.verbose)
            for k in totals:
                totals[k] += int(stats.get(k, 0))
            if src_hint is None and migration._src_ref is not None:
                src_hint = migration._src_ref[0]
            if dest_hint is None and migration._dest_ref is not None:
                dest_hint = migration._dest_ref[0]

        print("\n" + "=" * 60)
        print(f"Workspace-wide summary ({len(codes)} projects)")
        print("=" * 60)
        print(f"  Total test cases:         {totals['total']}")
        print(f"  Cases needing migration:  {totals['needs_migration']}")
        print(f"  Cases migrated:           {totals['migrated']}")
        print(f"  Cases skipped:            {totals['skipped']}")
        print(f"  Errors:                   {totals['errors']}")
        print("=" * 60)
    else:
        migration = QaseFieldMigration(
            api_token=api_token,
            project_code=str(project_code).strip(),
            source_field_name=source_field,
            destination_field_name=destination_field,
            destination_field_id=destination_field_id,
            clear_source=clear_source,
            base_url=base_url,
        )
        migration.run(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
