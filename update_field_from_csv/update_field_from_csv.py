#!/usr/bin/env python3
"""
Qase Migration Script: Update Custom Fields from CSV

This script:
1. Reads a CSV file with test case IDs and field values
2. Fetches all test cases from a Qase project
3. Matches CSV IDs (codes) to Qase test cases
4. Updates the specified custom field for each matched test case
"""

import csv
import json
import os
import argparse
import re
from typing import Dict, Optional, Any, List

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qase_api import (
    QaseAPI,
    resolve_qase_base_url,
    list_workspace_project_codes,
    confirm_run_all_projects,
)


class CSVFieldUpdater:
    """Main class for updating custom fields from CSV file."""

    def __init__(
        self,
        api_token: str,
        project_code: str,
        csv_file_path: str,
        field_name: str,
        field_id: Optional[int] = None,
        csv_column_name: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize the updater.

        Args:
            api_token: Qase API token
            project_code: Project code (e.g., 'CR')
            csv_file_path: Path to the CSV file
            field_name: Name of the custom field to update
            field_id: Optional custom field ID (if not provided, will search by name)
            csv_column_name: Name of the CSV column to read (defaults to field_name)
        """
        self.api = QaseAPI(api_token, project_code, base_url)
        self.csv_file_path = csv_file_path
        self.field_name = field_name
        self.field_id = field_id
        self.csv_column_name = csv_column_name or field_name

    @staticmethod
    def strip_html_tags(text: str) -> str:
        """
        Remove HTML tags from text while preserving line breaks and content.
        
        Args:
            text: Text that may contain HTML tags
            
        Returns:
            Text with HTML tags removed, preserving line breaks
        """
        if not text:
            return text
        
        # Remove HTML tags using regex
        # This pattern matches <tag>content</tag> and removes the tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Preserve newlines but clean up extra spaces within lines
        # Replace multiple spaces (but not newlines) with single space
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Clean up multiple spaces within each line
            cleaned_line = re.sub(r'[ \t]+', ' ', line.strip())
            cleaned_lines.append(cleaned_line)
        
        # Join lines back together, preserving single newlines
        text = '\n'.join(cleaned_lines)
        
        # Clean up excessive consecutive newlines (more than 2) to max 2
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    def load_csv_data(self) -> Dict[str, str]:
        """
        Load test case IDs and field values from CSV file.

        Returns:
            Dictionary mapping test case codes to field values
        """
        csv_data = {}
        
        if not os.path.exists(self.csv_file_path):
            raise FileNotFoundError(f"CSV file not found: {self.csv_file_path}")

        print(f"Reading CSV file: {self.csv_file_path}")
        print(f"Looking for CSV column: '{self.csv_column_name}'")
        
        with open(self.csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Check if the column exists
            if self.csv_column_name not in reader.fieldnames:
                available_columns = ', '.join(reader.fieldnames or [])
                raise ValueError(
                    f"CSV column '{self.csv_column_name}' not found in CSV file. "
                    f"Available columns: {available_columns}"
                )
            
            for row in reader:
                case_code = row.get('ID', '').strip()
                field_value = row.get(self.csv_column_name, '').strip()
                
                # Strip HTML tags from field value
                field_value = self.strip_html_tags(field_value)
                
                if case_code:
                    csv_data[case_code] = field_value
        
        print(f"Loaded {len(csv_data)} test cases from CSV")
        return csv_data

    def find_field_id(self) -> Optional[int]:
        """
        Find the custom field ID for the specified field.
        Uses the provided ID from config if available, otherwise searches by name.

        Returns:
            Field ID if found, None otherwise
        """
        if self.field_id is not None:
            print(f"Using {self.field_name} custom field ID: {self.field_id}")
            return self.field_id

        print(f"Fetching custom field definitions to find '{self.field_name}'...")
        custom_fields = self.api.get_custom_fields()

        for field in custom_fields:
            title = field.get("title", "")
            # Try exact match first, then case-insensitive
            if title == self.field_name or title.lower() == self.field_name.lower():
                field_id = field.get("id")
                if field_id:
                    self.field_id = field_id
                    print(f"Found '{self.field_name}' custom field with ID: {field_id}")
                    return field_id

        print(f"Warning: '{self.field_name}' custom field not found!")
        return None

    def process_updates(self, dry_run: bool = False, verbose: bool = False) -> Dict[str, int]:
        """
        Process CSV data and update test cases.

        Args:
            dry_run: If True, don't make actual updates
            verbose: If True, show detailed information about each case

        Returns:
            Dictionary with statistics about the update
        """
        # Load CSV data
        csv_data = self.load_csv_data()
        
        if not csv_data:
            print("No data found in CSV file!")
            return {
                "total_csv_rows": 0,
                "matched": 0,
                "updated": 0,
                "errors": 0,
                "not_found": 0,
                "skipped": 0,
                "matched_codes": set(),
            }

        field_id = self.find_field_id()
        if not field_id:
            print(f"Error: Cannot proceed without finding the '{self.field_name}' custom field.")
            return {
                "total_csv_rows": len(csv_data),
                "matched": 0,
                "updated": 0,
                "errors": 0,
                "not_found": 0,
                "skipped": 0,
                "matched_codes": set(),
            }

        # Fetch all test cases
        test_cases = self.api.get_all_test_cases()
        
        # Create a mapping of test case codes to test case objects
        # Map both with and without "C" prefix to handle different formats
        test_case_map = {}
        sample_codes = []
        for test_case in test_cases:
            # Try different possible field names for the code
            case_code = test_case.get("code") or test_case.get("case_code") or test_case.get("id")
            if case_code:
                # Convert to string
                case_code_str = str(case_code)
                # Store with the code as-is
                test_case_map[case_code_str] = test_case
                # Also store with "C" prefix if it doesn't have one (for CSV matching)
                if not case_code_str.startswith("C"):
                    test_case_map[f"C{case_code_str}"] = test_case
                # Also store without "C" prefix if it has one
                elif case_code_str.startswith("C"):
                    test_case_map[case_code_str[1:]] = test_case
                
                if len(sample_codes) < 5:
                    sample_codes.append(case_code_str)
        
        # Debug: Show sample codes to help diagnose matching issues
        if len(test_case_map) > 0:
            print(f"\nFound {len(test_case_map)} test cases with codes in Qase project")
            print(f"Sample Qase codes: {sample_codes[:5]}")
            if len(csv_data) > 0:
                csv_codes_sample = list(csv_data.keys())[:5]
                print(f"Sample CSV codes: {csv_codes_sample}")
        else:
            print(f"\nWarning: No test cases with 'code' field found.")
            if len(test_cases) > 0:
                print(f"Sample test case keys: {list(test_cases[0].keys())[:10]}")
                if verbose:
                    print(f"Sample test case: {json.dumps(test_cases[0], indent=2, default=str)[:500]}")

        print(f"Matching CSV data to Qase test cases...")

        stats: Dict[str, Any] = {
            "total_csv_rows": len(csv_data),
            "matched": 0,
            "updated": 0,
            "errors": 0,
            "not_found": 0,
            "skipped": 0,
            "matched_codes": set(),
        }

        for case_code, csv_field_value in csv_data.items():
            # Try to find test case with CSV code as-is, with "C" prefix, or without "C" prefix
            test_case = test_case_map.get(case_code)
            if not test_case and case_code.startswith("C"):
                # Try without "C" prefix
                test_case = test_case_map.get(case_code[1:])
            if not test_case and not case_code.startswith("C"):
                # Try with "C" prefix
                test_case = test_case_map.get(f"C{case_code}")
            
            if not test_case:
                stats["not_found"] += 1
                if verbose:
                    print(f"  [WARNING] Test case {case_code} not found in Qase project")
                continue

            stats["matched"] += 1
            stats["matched_codes"].add(case_code)
            case_id = test_case.get("id")
            title = test_case.get("title", "Untitled")
            
            # Check current field value (for display purposes only)
            current_field_value = ""
            custom_fields = test_case.get("custom_fields", [])
            for field in custom_fields:
                if field.get("id") == field_id:
                    current_field_value = field.get("value", "")
                    break

            # Always update with CSV value (don't skip even if values match)
            # This ensures CSV is the source of truth

            # Prepare update
            updates = {
                "custom_field": {
                    str(field_id): csv_field_value
                }
            }

            if verbose:
                print(f"\n  Case {case_code} ({case_id}): '{title}'")
                current_display = current_field_value[:100] + ('...' if len(current_field_value) > 100 else '')
                csv_display = csv_field_value[:100] + ('...' if len(csv_field_value) > 100 else '')
                print(f"    Current: {current_display}")
                print(f"    Updating: {csv_display}")

            if not dry_run:
                if self.api.update_test_case(case_id, updates):
                    stats["updated"] += 1
                    print(f"  [OK] Successfully updated case {case_code} ({case_id})")
                else:
                    stats["errors"] += 1
                    print(f"  [ERROR] Failed to update case {case_code} ({case_id})")
            else:
                print(f"  [DRY RUN] Would update case {case_code} ({case_id}) with {self.field_name}")
                stats["updated"] += 1  # Count as would-be updated in dry run

        return stats

    def run(self, dry_run: bool = False, verbose: bool = False) -> Dict[str, Any]:
        """Main execution method. Returns per-project stats."""
        print("=" * 60)
        print(f"Qase Custom Field CSV Updater — project: {self.api.project_code}")
        print("=" * 60)
        print(f"CSV file: {self.csv_file_path}")
        print(f"Field name: {self.field_name}")
        print(f"CSV column: {self.csv_column_name}")
        if dry_run:
            print("DRY RUN MODE - No changes will be made")
        if verbose:
            print("VERBOSE MODE - Showing detailed information")
        print()

        stats = self.process_updates(dry_run=dry_run, verbose=verbose)

        print("\n" + "-" * 60)
        print(f"Summary for project {self.api.project_code}:")
        print(f"  Total CSV rows:           {stats['total_csv_rows']}")
        print(f"  Matched in this project:  {stats['matched']}")
        print(f"  Updated:                  {stats['updated']}")
        print(f"  Skipped (already match):  {stats['skipped']}")
        print(f"  Not matched here:         {stats['not_found']}")
        print(f"  Errors:                   {stats['errors']}")
        return stats


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
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
        description="Update custom field in Qase test cases from CSV file"
    )
    parser.add_argument(
        "csv_file",
        help="Path to CSV file with ID and field value columns"
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
        help=(
            "Qase project code (overrides config file). "
            "Use 'all' to iterate every project in the workspace — each "
            "CSV row will be applied to whichever project its test case "
            "code lives in."
        ),
    )
    parser.add_argument(
        "--host",
        help="Qase API host (overrides config 'host'; default api.qase.io or from config)",
    )
    parser.add_argument(
        "--field-name",
        default=None,
        help="Name of the custom field to update (default: from config.json or 'Postconditions')"
    )
    parser.add_argument(
        "--field-id",
        type=int,
        help="Custom field ID (overrides name search)"
    )
    parser.add_argument(
        "--csv-column",
        help="Name of the CSV column to read (defaults to field name)"
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

    # Load config from file
    api_token = args.token
    project_code = args.project
    field_id = args.field_id
    field_name = args.field_name
    csv_column_name = args.csv_column
    config: Optional[Dict[str, Any]] = None

    try:
        config = load_config(args.config)
        api_token = api_token or config.get("api_token")
        project_code = project_code or config.get("project_code")
        
        # Get field name from config if not provided via CLI
        # Priority: CLI argument > config.json > default ("Postconditions")
        if not field_name:
            config_field_name = config.get("csv_field_name") or config.get("csv_update_field")
            if config_field_name:
                field_name = config_field_name
            else:
                field_name = "Postconditions"  # Default fallback
        
        # Get field ID from config if not provided via CLI
        if not field_id:
            config_field_id = config.get("csv_field_id") or config.get("csv_update_field_id")
            if config_field_id is not None:
                try:
                    field_id = int(config_field_id)
                except (ValueError, TypeError):
                    field_id = None
        
        # Get CSV column name from config if not provided via CLI
        if not csv_column_name:
            config_csv_column = config.get("csv_column_name")
            if config_csv_column:
                csv_column_name = config_csv_column
    except (FileNotFoundError, ValueError) as e:
        # Only error if we don't have required fields from CLI
        if not api_token or not project_code:
            parser.error(
                f"Either provide --token and --project arguments, "
                f"or create a valid config file. Error: {e}"
            )

    if not api_token:
        parser.error("API token is required (provide via --token or config file)")
    if not project_code:
        parser.error("Project code is required (provide via --project or config file)")

    # Ensure field_name is set
    if not field_name:
        field_name = "Postconditions"

    base_url = resolve_qase_base_url(args.host, config, args.config)

    if str(project_code).strip().lower() == "all":
        if field_id is not None:
            print(
                "[WARN] 'csv_field_id' / --field-id is project-specific and "
                "is ignored when project_code='all'. The field will be "
                "resolved by name in every project."
            )
            field_id = None

        codes = list_workspace_project_codes(api_token, base_url)
        if not codes:
            parser.error("No projects returned by the API.")
        if not confirm_run_all_projects(
            codes,
            action=f"update '{field_name}' on test cases in",
            dry_run=args.dry_run,
        ):
            print("Aborted.")
            return

        totals = {"total_csv_rows": 0, "matched": 0, "updated": 0,
                  "skipped": 0, "errors": 0}
        matched_codes_overall: set = set()

        for code in codes:
            updater = CSVFieldUpdater(
                api_token=api_token,
                project_code=code,
                csv_file_path=args.csv_file,
                field_name=field_name,
                field_id=None,
                csv_column_name=csv_column_name,
                base_url=base_url,
            )
            stats = updater.run(dry_run=args.dry_run, verbose=args.verbose)
            totals["total_csv_rows"] = int(stats.get("total_csv_rows", 0))
            for k in ("matched", "updated", "skipped", "errors"):
                totals[k] += int(stats.get(k, 0))
            matched_codes_overall.update(stats.get("matched_codes") or set())

        not_found_in_workspace = max(
            totals["total_csv_rows"] - len(matched_codes_overall), 0
        )

        print("\n" + "=" * 60)
        print(f"Workspace-wide summary ({len(codes)} projects)")
        print("=" * 60)
        print(f"  Total CSV rows:                   {totals['total_csv_rows']}")
        print(f"  Unique CSV rows matched:          {len(matched_codes_overall)}")
        print(f"  CSV rows not found in workspace:  {not_found_in_workspace}")
        print(f"  Total per-project updates:        {totals['updated']}")
        print(f"  Skipped:                          {totals['skipped']}")
        print(f"  Errors:                           {totals['errors']}")
        print("=" * 60)
    else:
        updater = CSVFieldUpdater(
            api_token=api_token,
            project_code=str(project_code).strip(),
            csv_file_path=args.csv_file,
            field_name=field_name,
            field_id=field_id,
            csv_column_name=csv_column_name,
            base_url=base_url,
        )
        updater.run(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
