"""
CSV Reference Fixer

Handles the logic for finding and fixing broken CSV file references in test cases.
Also provides migration orchestration for processing all test cases.
"""

import re
import json
import os
import argparse
from typing import Dict, List, Any, Optional, Tuple

from qase_api import QaseAPI, resolve_qase_base_url


class CSVFixer:
    """Handles fixing broken CSV references in test case fields and migration orchestration."""

    def __init__(
        self,
        api_token: Optional[str] = None,
        project_code: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize the CSV fixer.

        Args:
            api_token: Qase API token (optional, required for migration)
            project_code: Project code (optional, required for migration)
            base_url: Qase API base URL (e.g. https://api.qase.io/v1)
        """
        self.api = (
            QaseAPI(api_token, project_code, base_url)
            if api_token and project_code
            else None
        )

    @staticmethod
    def find_broken_csv_references(text: Optional[str]) -> List[Tuple[str, str]]:
        """
        Find broken CSV references in text.

        Args:
            text: Text to search for broken CSV references

        Returns:
            List of tuples: (broken_pattern, fixed_pattern)
            Broken format: ![filename.csv](url) or fully escaped markdown
            Fixed format: [filename.csv](url)
        """
        if not text:
            return []

        broken_refs = []
        
        # Pattern 1: Match unescaped broken references: ![filename.csv](url)
        pattern1 = r'(?<!\\)!\[([^\]]+\.csv[^\]]*)\]\(([^\)]+)\)'
        
        # Pattern 2: Match escaped broken references: \![filename.csv](url)
        # (where ! is escaped but brackets/parens are not)
        pattern2 = r'\\!\[([^\]]+\.csv[^\]]*)\]\(([^\)]+)\)'
        
        # Pattern 3: Match fully escaped markdown: \!\[filename\.csv\]\(url\)
        # This handles cases where all markdown syntax is escaped
        # Match: backslash-exclamation-backslash-bracket, then filename with .csv, 
        # then backslash-bracket-backslash-paren, then URL, then backslash-paren
        # Use a more flexible pattern that allows escaped chars in filename/URL
        pattern3 = r'\\!\\\[(.*?\.csv.*?)\\\]\\\((.*?)\\\)'

        # Check for unescaped broken references
        matches = re.finditer(pattern1, text)
        for match in matches:
            filename = match.group(1)
            url = match.group(2)
            broken_pattern = match.group(0)
            fixed_pattern = f"[{filename}]({url})"
            broken_refs.append((broken_pattern, fixed_pattern))

        # Check for escaped ! but unescaped brackets
        matches = re.finditer(pattern2, text)
        for match in matches:
            filename = match.group(1)
            url = match.group(2)
            broken_pattern = match.group(0)  # Includes the backslash before !
            fixed_pattern = f"[{filename}]({url})"
            broken_refs.append((broken_pattern, fixed_pattern))

        # Check for fully escaped markdown (all syntax escaped)
        matches = re.finditer(pattern3, text)
        for match in matches:
            # The filename and URL have escaped characters that need to be unescaped
            filename_raw = match.group(1)
            url_raw = match.group(2)
            # Unescape common escaped characters in filename
            # Order matters: do \\\\ first, then other escapes
            filename = filename_raw.replace('\\\\', '\\').replace('\\_', '_').replace('\\(', '(').replace('\\)', ')').replace('\\.', '.')
            # Unescape URL - handle all escaped characters including those in the path
            url = url_raw.replace('\\\\', '\\').replace('\\_', '_').replace('\\(', '(').replace('\\)', ')').replace('\\.', '.').replace('\\/', '/')
            broken_pattern = match.group(0)  # Full escaped pattern
            fixed_pattern = f"[{filename}]({url})"
            broken_refs.append((broken_pattern, fixed_pattern))

        return broken_refs

    @staticmethod
    def fix_text(text: Optional[str]) -> Optional[str]:
        """
        Fix broken CSV references in text by removing ! prefix.

        Args:
            text: Text that may contain broken CSV references

        Returns:
            Fixed text if changes were made, None otherwise
        """
        if not text:
            return None

        broken_refs = CSVFixer.find_broken_csv_references(text)
        if not broken_refs:
            return None

        fixed_text = text
        for broken, fixed in broken_refs:
            fixed_text = fixed_text.replace(broken, fixed)

        return fixed_text if fixed_text != text else None

    @staticmethod
    def analyze_test_case(test_case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a test case and return fields that need to be updated.

        Args:
            test_case: Test case dictionary from the API

        Returns:
            Dictionary with only the fields that need fixing
        """
        updates = {}

        # Check description
        description = test_case.get("description")
        fixed_description = CSVFixer.fix_text(description)
        if fixed_description:
            updates["description"] = fixed_description

        # Check preconditions
        preconditions = test_case.get("preconditions")
        fixed_preconditions = CSVFixer.fix_text(preconditions)
        if fixed_preconditions:
            updates["preconditions"] = fixed_preconditions

        # Check postconditions
        postconditions = test_case.get("postconditions")
        fixed_postconditions = CSVFixer.fix_text(postconditions)
        if fixed_postconditions:
            updates["postconditions"] = fixed_postconditions

        # Check steps
        steps = test_case.get("steps", [])
        if steps:
            fixed_steps = []
            steps_need_update = False

            for step in steps:
                # Build the step update object with only fields that need to be sent
                fixed_step = {}
                step_updated = False

                # Include position (required for step identification)
                if "position" in step:
                    fixed_step["position"] = step["position"]
                
                # Include hash if it exists (may be required for step updates)
                if "hash" in step:
                    fixed_step["hash"] = step["hash"]

                # Check action field
                action = step.get("action")
                fixed_action = CSVFixer.fix_text(action)
                if fixed_action:
                    fixed_step["action"] = fixed_action
                    step_updated = True
                elif action is not None:
                    fixed_step["action"] = action

                # Check expected_result field
                expected_result = step.get("expected_result")
                fixed_expected_result = CSVFixer.fix_text(expected_result)
                if fixed_expected_result:
                    fixed_step["expected_result"] = fixed_expected_result
                    step_updated = True
                elif expected_result is not None:
                    fixed_step["expected_result"] = expected_result

                # Check data field
                data = step.get("data")
                fixed_data = CSVFixer.fix_text(data)
                if fixed_data:
                    fixed_step["data"] = fixed_data
                    step_updated = True
                elif data is not None:
                    fixed_step["data"] = data

                if step_updated:
                    steps_need_update = True

                # Always include the step in the array to maintain structure
                fixed_steps.append(fixed_step)

            if steps_need_update:
                updates["steps"] = fixed_steps

        # Check custom_fields
        # Note: API expects "custom_field" (singular) as an object with field IDs as keys
        custom_fields = test_case.get("custom_fields", [])
        if custom_fields:
            custom_field_updates = {}
            custom_fields_need_update = False

            for field in custom_fields:
                field_id = field.get("id")
                value = field.get("value")
                fixed_value = CSVFixer.fix_text(value)
                if fixed_value and field_id is not None:
                    # API expects field ID as string key
                    custom_field_updates[str(field_id)] = fixed_value
                    custom_fields_need_update = True

            if custom_fields_need_update:
                updates["custom_field"] = custom_field_updates

        return updates

    def process_all_cases(self, dry_run: bool = False, verbose: bool = False) -> Dict[str, int]:
        """
        Process all test cases and fix broken CSV references.

        Args:
            dry_run: If True, don't make actual updates
            verbose: If True, show detailed information about each case

        Returns:
            Dictionary with statistics about the migration

        Raises:
            ValueError: If API token or project code not provided during initialization
        """
        if not self.api:
            raise ValueError("API token and project code must be provided during initialization for migration")

        test_cases = self.api.get_all_test_cases()
        stats = {
            "total": len(test_cases),
            "needs_fixing": 0,
            "fixed": 0,
            "errors": 0
        }

        print(f"\nAnalyzing {stats['total']} test cases...")

        for test_case in test_cases:
            case_id = test_case.get("id")
            title = test_case.get("title", "Untitled")

            updates = self.analyze_test_case(test_case)

            if verbose:
                # Show what fields were checked and if they have broken refs
                desc = test_case.get("description", "")
                prec = test_case.get("preconditions", "")
                postc = test_case.get("postconditions", "")
                steps = test_case.get("steps", [])
                custom = test_case.get("custom_fields", [])
                
                desc_broken = self.find_broken_csv_references(desc)
                prec_broken = self.find_broken_csv_references(prec)
                postc_broken = self.find_broken_csv_references(postc)
                steps_broken = sum(len(self.find_broken_csv_references(s.get("action", "") or s.get("expected_result", "") or s.get("data", ""))) for s in steps)
                custom_broken = sum(len(self.find_broken_csv_references(f.get("value", ""))) for f in custom)
                
                print(f"Case {case_id} ('{title}'): desc={len(desc_broken)}, prec={len(prec_broken)}, postc={len(postc_broken)}, steps={steps_broken}, custom={custom_broken}")

            if updates:
                stats["needs_fixing"] += 1
                print(f"\nCase {case_id} ('{title}') needs fixing:")
                print(f"  Fields to update: {list(updates.keys())}")

                if not dry_run:
                    if self.api.update_test_case(case_id, updates):
                        stats["fixed"] += 1
                        print(f"  ✓ Successfully updated case {case_id}")
                    else:
                        stats["errors"] += 1
                        print(f"  ✗ Failed to update case {case_id}")
                else:
                    print(f"  [DRY RUN] Would update with: {json.dumps(updates, indent=2)}")
                    stats["fixed"] += 1  # Count as would-be fixed in dry run

        return stats

    def run(self, dry_run: bool = False, verbose: bool = False):
        """
        Main execution method for migration.

        Args:
            dry_run: If True, don't make actual updates
            verbose: If True, show detailed information about each case

        Raises:
            ValueError: If API token or project code not provided during initialization
        """
        print("=" * 60)
        print("Qase CSV Reference Fixer")
        print("=" * 60)
        if dry_run:
            print("DRY RUN MODE - No changes will be made")
        if verbose:
            print("VERBOSE MODE - Showing detailed analysis")
        print()

        stats = self.process_all_cases(dry_run=dry_run, verbose=verbose)

        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  Total test cases: {stats['total']}")
        print(f"  Cases needing fixes: {stats['needs_fixing']}")
        print(f"  Cases fixed: {stats['fixed']}")
        print(f"  Errors: {stats['errors']}")
        if stats['needs_fixing'] == 0 and stats['total'] > 0:
            print("\n  [INFO] All test cases are already fixed! No broken CSV references found.")
        print("=" * 60)


def load_config(config_path: str = "config.json") -> Dict[str, str]:
    """
    Load configuration from a JSON file.

    Args:
        config_path: Path to the config file

    Returns:
        Dictionary with configuration values

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid or missing required fields
    """
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
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fix broken CSV file references in Qase test cases"
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file (default: config.json)"
    )
    parser.add_argument(
        "--token",
        help="Qase API token (overrides config file)"
    )
    parser.add_argument(
        "--project",
        help="Qase project code (overrides config file)"
    )
    parser.add_argument(
        "--host",
        help="Qase API host (overrides config 'host'; default api.qase.io or from config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without making changes"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed information about each test case"
    )

    args = parser.parse_args()

    # Load config from file if token/project not provided via CLI
    api_token = args.token
    project_code = args.project
    config: Optional[Dict[str, Any]] = None

    if not api_token or not project_code:
        try:
            config = load_config(args.config)
            api_token = api_token or config.get("api_token")
            project_code = project_code or config.get("project_code")
        except (FileNotFoundError, ValueError) as e:
            if not api_token or not project_code:
                parser.error(
                    f"Either provide --token and --project arguments, "
                    f"or create a valid config file. Error: {e}"
                )

    if not api_token:
        parser.error("API token is required (provide via --token or config file)")
    if not project_code:
        parser.error("Project code is required (provide via --project or config file)")

    base_url = resolve_qase_base_url(args.host, config, args.config)

    fixer = CSVFixer(
        api_token=api_token,
        project_code=project_code,
        base_url=base_url,
    )

    fixer.run(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
