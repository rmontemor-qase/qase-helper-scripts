#!/usr/bin/env python3
"""
Qase Field Migration Script

This script migrates field content from system fields to custom fields in Qase test cases.
It can be used to migrate any system field to any custom field by configuring the source
and destination fields in config.json or via command-line arguments.

This script:
1. Fetches all test cases from a Qase project
2. Gets the content from a specified system field
3. Copies it to a specified custom field
4. Clears the source system field
5. Updates the test cases via PATCH requests
"""

import json
import os
import argparse
from typing import Dict, Optional, Any

from qase_api import QaseAPI, resolve_qase_base_url


class QaseFieldMigration:
    """Main class for migrating field content from system fields to custom fields."""

    def __init__(
        self,
        api_token: str,
        project_code: str,
        source_field_name: str,
        destination_field_name: str,
        destination_field_id: Optional[int] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize the migration tool.

        Args:
            api_token: Qase API token
            project_code: Project code (e.g., 'CR')
            source_field_name: Name of the source system field (e.g., 'Pre-conditions', 'Description')
            destination_field_name: Name of the destination custom field (e.g., 'Preconditions')
            destination_field_id: Optional custom field ID (if not provided, will search by name)
        """
        self.api = QaseAPI(api_token, project_code, base_url)
        self.source_field_name = source_field_name
        self.destination_field_name = destination_field_name
        self.destination_field_id = destination_field_id
        self.source_field_slug = None

    def find_source_field_slug(self) -> Optional[str]:
        """
        Find the system field slug for the source field by name.

        Returns:
            Field slug if found, None otherwise
        """
        if self.source_field_slug is not None:
            return self.source_field_slug

        print(f"Fetching system field definitions to find '{self.source_field_name}'...")
        system_fields = self.api.get_system_fields()

        for field in system_fields:
            title = field.get("title", "")
            slug = field.get("slug", "")
            # Try exact match first, then case-insensitive
            if (title == self.source_field_name or 
                title.lower() == self.source_field_name.lower() or
                slug.lower() == self.source_field_name.lower()):
                self.source_field_slug = slug
                print(f"Found '{self.source_field_name}' system field with slug: {slug}")
                return slug

        print(f"Warning: '{self.source_field_name}' system field not found!")
        return None

    def find_destination_field_id(self) -> Optional[int]:
        """
        Find the custom field ID for the destination field.
        Uses the provided ID from config if available, otherwise searches by name.

        Returns:
            Field ID if found, None otherwise
        """
        if self.destination_field_id is not None:
            print(f"Using {self.destination_field_name} custom field ID from config: {self.destination_field_id}")
            return self.destination_field_id

        print(f"Fetching custom field definitions to find '{self.destination_field_name}'...")
        custom_fields = self.api.get_custom_fields()

        for field in custom_fields:
            title = field.get("title", "")
            # Try exact match first, then case-insensitive
            if title == self.destination_field_name or title.lower() == self.destination_field_name.lower():
                field_id = field.get("id")
                if field_id:
                    self.destination_field_id = field_id
                    print(f"Found '{self.destination_field_name}' custom field with ID: {field_id}")
                    return field_id

        print(f"Warning: '{self.destination_field_name}' custom field not found!")
        return None

    @staticmethod
    def display_progress_bar(current: int, total: int, stats: Dict[str, int], bar_length: int = 40):
        """
        Display a progress bar with percentage and statistics.
        
        Args:
            current: Current progress count
            total: Total count
            stats: Dictionary with statistics (needs_migration, migrated, errors, skipped)
            bar_length: Length of the progress bar in characters
        """
        if total == 0:
            return
        
        percent = (current / total) * 100
        filled_length = int(bar_length * current // total)
        bar = '=' * filled_length + '>' + '-' * (bar_length - filled_length - 1)
        
        # Build stats string
        stats_str = f"Needs migration: {stats['needs_migration']}, Migrated: {stats['migrated']}, Errors: {stats['errors']}, Skipped: {stats['skipped']}"
        
        # Use \r to overwrite the same line
        print(f'\rProgress: [{bar}] {percent:.1f}% ({current}/{total}) | {stats_str}', end='', flush=True)
        
        # If we're done, print a newline
        if current == total:
            print()

    def analyze_test_case(self, test_case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Analyze a test case and return updates needed.

        Args:
            test_case: Test case dictionary from the API

        Returns:
            Dictionary with updates if needed, None otherwise
        """
        # Get the system field value using the slug
        source_value = test_case.get(self.source_field_slug, "")

        # If there's no content in source field, nothing to migrate
        if not source_value or not source_value.strip():
            return None

        # Prepare the update: copy to destination and clear source
        # We always migrate if source has content (even if destination already has it,
        # we still need to clear the source field)
        updates = {
            "custom_field": {
                str(self.destination_field_id): source_value
            },
            self.source_field_slug: ""  # Clear the source field
        }

        return updates

    def process_all_cases(self, dry_run: bool = False, verbose: bool = False) -> Dict[str, int]:
        """
        Process all test cases and migrate field content.

        Args:
            dry_run: If True, don't make actual updates
            verbose: If True, show detailed information about each case

        Returns:
            Dictionary with statistics about the migration
        """
        # First, find the source system field slug
        source_slug = self.find_source_field_slug()
        if not source_slug:
            print(f"Error: Cannot proceed without finding the '{self.source_field_name}' system field.")
            return {
                "total": 0,
                "needs_migration": 0,
                "migrated": 0,
                "errors": 0,
                "skipped": 0
            }

        # Then, find the destination custom field ID
        field_id = self.find_destination_field_id()
        if not field_id:
            print(f"Error: Cannot proceed without finding the '{self.destination_field_name}' custom field.")
            return {
                "total": 0,
                "needs_migration": 0,
                "migrated": 0,
                "errors": 0,
                "skipped": 0
            }

        test_cases = self.api.get_all_test_cases()
        stats = {
            "total": len(test_cases),
            "needs_migration": 0,
            "migrated": 0,
            "errors": 0,
            "skipped": 0
        }

        print(f"\nAnalyzing {stats['total']} test cases...")
        print(f"Migrating from '{self.source_field_name}' (slug: {source_slug}) to '{self.destination_field_name}' (ID: {field_id})")
        print()

        processed_count = 0
        
        for test_case in test_cases:
            processed_count += 1
            case_id = test_case.get("id")
            title = test_case.get("title", "Untitled")
            source_value = test_case.get(source_slug, "")

            # Update progress bar
            # In verbose mode, update less frequently to avoid cluttering output
            # In normal mode, update every case for smooth progress
            if verbose:
                # Update every 10 cases or at start/end
                if processed_count == 1 or processed_count % 10 == 0 or processed_count == stats['total']:
                    self.display_progress_bar(processed_count, stats['total'], stats)
            else:
                # Update every case for smooth progress
                self.display_progress_bar(processed_count, stats['total'], stats)

            if verbose:
                # Show what we're checking (on a new line to not interfere with progress bar)
                has_source_value = bool(source_value and source_value.strip())
                custom_fields = test_case.get("custom_fields", [])
                current_custom_value = ""
                for field in custom_fields:
                    if field.get("id") == self.destination_field_id:
                        current_custom_value = field.get("value", "")
                        break
                
                print(f"\nCase {case_id} ('{title}'): "
                      f"{self.source_field_name}={('yes' if has_source_value else 'no')}, "
                      f"{self.destination_field_name}={('set' if current_custom_value else 'empty')}")

            updates = self.analyze_test_case(test_case)

            if updates:
                stats["needs_migration"] += 1
                if verbose:
                    print(f"\nCase {case_id} ('{title}') needs migration:")
                    print(f"  {self.source_field_name} value: {source_value[:100]}{'...' if len(source_value) > 100 else ''}")

                if not dry_run:
                    if self.api.update_test_case(case_id, updates):
                        stats["migrated"] += 1
                        if verbose:
                            print(f"  ✓ Successfully migrated case {case_id} (copied to {self.destination_field_name} and cleared {self.source_field_name})")
                    else:
                        stats["errors"] += 1
                        print(f"\n  ✗ Failed to migrate case {case_id}")
                else:
                    if verbose:
                        print(f"  [DRY RUN] Would:")
                        print(f"    - Update custom field {self.destination_field_id} ({self.destination_field_name}) with {self.source_field_name} value")
                        print(f"    - Clear {self.source_field_name} field")
                    stats["migrated"] += 1  # Count as would-be migrated in dry run
            else:
                if source_value and source_value.strip():
                    # Has source value but custom field already has the same value and source is already empty
                    # (This case shouldn't happen due to our logic, but keeping for safety)
                    stats["skipped"] += 1
                elif verbose:
                    print(f"\nCase {case_id} ('{title}'): No {self.source_field_name} to migrate")
        
        # Final progress bar update
        self.display_progress_bar(processed_count, stats['total'], stats)

        return stats

    def run(self, dry_run: bool = False, verbose: bool = False):
        """
        Main execution method.

        Args:
            dry_run: If True, don't make actual updates
            verbose: If True, show detailed information about each case
        """
        print("=" * 60)
        print("Qase Field Migration")
        print("=" * 60)
        print(f"Source field: {self.source_field_name}")
        print(f"Destination field: {self.destination_field_name}")
        if dry_run:
            print("DRY RUN MODE - No changes will be made")
        if verbose:
            print("VERBOSE MODE - Showing detailed analysis")
        print()

        stats = self.process_all_cases(dry_run=dry_run, verbose=verbose)

        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  Total test cases: {stats['total']}")
        print(f"  Cases needing migration: {stats['needs_migration']}")
        print(f"  Cases migrated: {stats['migrated']}")
        print(f"  Cases skipped (already migrated): {stats['skipped']}")
        print(f"  Errors: {stats['errors']}")
        if stats['needs_migration'] == 0 and stats['total'] > 0:
            print(f"\n  [INFO] All test cases are already migrated! No {self.source_field_name} to migrate.")
        print("=" * 60)


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
        description="Migrate field content from system fields to custom fields in Qase test cases"
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
        "--source-field",
        help="Name of the source system field (e.g., 'preconditions', 'description'). Can also be set in config.json"
    )
    parser.add_argument(
        "--destination-field",
        help="Name of the destination custom field (e.g., 'Preconditions'). Can also be set in config.json"
    )
    parser.add_argument(
        "--destination-field-id",
        type=int,
        help="Custom field ID for destination field (overrides config file and name search)"
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
    source_field = args.source_field
    destination_field = args.destination_field
    destination_field_id = args.destination_field_id
    config: Optional[Dict[str, Any]] = None

    try:
        config = load_config(args.config)
        api_token = api_token or config.get("api_token")
        project_code = project_code or config.get("project_code")
        source_field = source_field or config.get("source_field")
        destination_field = destination_field or config.get("destination_field")
        # Get field ID from config if not provided via CLI
        if destination_field_id is None and "destination_field_id" in config:
            field_id_value = config.get("destination_field_id")
            # Convert to int if it's a number, otherwise keep as None
            if field_id_value is not None:
                try:
                    destination_field_id = int(field_id_value)
                except (ValueError, TypeError):
                    destination_field_id = None
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

    if not source_field:
        parser.error("Source field name is required (provide via --source-field or set 'source_field' in config.json)")
    if not destination_field:
        parser.error("Destination field name is required (provide via --destination-field or set 'destination_field' in config.json)")

    base_url = resolve_qase_base_url(args.host, config, args.config)

    migration = QaseFieldMigration(
        api_token=api_token,
        project_code=project_code,
        source_field_name=source_field,
        destination_field_name=destination_field,
        destination_field_id=destination_field_id,
        base_url=base_url,
    )

    migration.run(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
