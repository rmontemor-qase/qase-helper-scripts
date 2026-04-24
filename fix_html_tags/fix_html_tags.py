#!/usr/bin/env python3
"""
Fix HTML Tags in Test Cases

This script removes HTML tags (like <p>...</p>) from all text fields
in Qase test cases, including description, preconditions, postconditions,
steps, and custom fields.
"""

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


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Load configuration from a JSON file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file '{config_path}' not found.")

    with open(config_path, 'r') as f:
        config = json.load(f)

    if "api_token" not in config:
        raise ValueError("Config file must contain 'api_token' field")
    if "project_code" not in config:
        raise ValueError("Config file must contain 'project_code' field")

    return config


def analyze_test_case(test_case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a test case and return fields that need HTML tag removal.
    
    Args:
        test_case: Test case dictionary from the API
        
    Returns:
        Dictionary with only the fields that need fixing
    """
    updates = {}
    
    # Check description
    description = test_case.get("description")
    if description:
        cleaned_description = strip_html_tags(description)
        if description != cleaned_description:
            updates["description"] = cleaned_description
    
    # Check preconditions
    preconditions = test_case.get("preconditions")
    if preconditions:
        cleaned_preconditions = strip_html_tags(preconditions)
        if preconditions != cleaned_preconditions:
            updates["preconditions"] = cleaned_preconditions
    
    # Check postconditions
    postconditions = test_case.get("postconditions")
    if postconditions:
        cleaned_postconditions = strip_html_tags(postconditions)
        if postconditions != cleaned_postconditions:
            updates["postconditions"] = cleaned_postconditions
    
    # Check steps
    steps = test_case.get("steps", [])
    if steps:
        fixed_steps = []
        steps_need_update = False
        
        for step in steps:
            fixed_step = {}
            step_updated = False
            
            # Include position (required for step identification)
            if "position" in step:
                fixed_step["position"] = step["position"]
            
            # Include hash if it exists
            if "hash" in step:
                fixed_step["hash"] = step["hash"]
            
            # Check action field
            action = step.get("action")
            if action:
                cleaned_action = strip_html_tags(action)
                if action != cleaned_action:
                    fixed_step["action"] = cleaned_action
                    step_updated = True
                elif action is not None:
                    fixed_step["action"] = action
            
            # Check expected_result field
            expected_result = step.get("expected_result")
            if expected_result:
                cleaned_expected_result = strip_html_tags(expected_result)
                if expected_result != cleaned_expected_result:
                    fixed_step["expected_result"] = cleaned_expected_result
                    step_updated = True
                elif expected_result is not None:
                    fixed_step["expected_result"] = expected_result
            
            # Check data field
            data = step.get("data")
            if data:
                cleaned_data = strip_html_tags(data)
                if data != cleaned_data:
                    fixed_step["data"] = cleaned_data
                    step_updated = True
                elif data is not None:
                    fixed_step["data"] = data
            
            if step_updated:
                steps_need_update = True
            
            fixed_steps.append(fixed_step)
        
        if steps_need_update:
            updates["steps"] = fixed_steps
    
    # Check custom_fields
    custom_fields = test_case.get("custom_fields", [])
    if custom_fields:
        custom_field_updates = {}
        custom_fields_need_update = False
        
        for field in custom_fields:
            field_id = field.get("id")
            value = field.get("value")
            if value and field_id is not None:
                cleaned_value = strip_html_tags(value)
                if value != cleaned_value:
                    custom_field_updates[str(field_id)] = cleaned_value
                    custom_fields_need_update = True
        
        if custom_fields_need_update:
            updates["custom_field"] = custom_field_updates
    
    return updates


def _run_for_project(
    api_token: str,
    project_code: str,
    base_url: str,
    dry_run: bool,
    verbose: bool,
) -> Dict[str, Any]:
    """Run the HTML-tag cleanup against a single project; return stats."""
    api = QaseAPI(api_token, project_code, base_url)

    print("\n" + "=" * 60)
    print(f"Qase HTML-tag cleanup — project: {project_code}")
    print("=" * 60)
    print(f"Fetching test cases from project '{project_code}'...")
    test_cases = api.get_all_test_cases()

    stats = {
        "total": len(test_cases),
        "has_html": 0,
        "fixed": 0,
        "errors": 0,
        "skipped": 0,
        "fields_fixed": {
            "description": 0,
            "preconditions": 0,
            "postconditions": 0,
            "steps": 0,
            "custom_fields": 0,
        },
    }

    print(f"Analyzing {stats['total']} test cases for HTML tags in all fields...")

    for test_case in test_cases:
        case_id = test_case.get("id")
        case_code = test_case.get("code", "")
        title = test_case.get("title", "Untitled")

        updates = analyze_test_case(test_case)

        if updates:
            stats["has_html"] += 1
            if "description" in updates:
                stats["fields_fixed"]["description"] += 1
            if "preconditions" in updates:
                stats["fields_fixed"]["preconditions"] += 1
            if "postconditions" in updates:
                stats["fields_fixed"]["postconditions"] += 1
            if "steps" in updates:
                stats["fields_fixed"]["steps"] += 1
            if "custom_field" in updates:
                stats["fields_fixed"]["custom_fields"] += len(updates["custom_field"])

            if verbose:
                print(f"\n  Case {case_code} ({case_id}): '{title}'")
                print(f"    Fields to fix: {list(updates.keys())}")
                if "custom_field" in updates:
                    print(f"    Custom fields: {len(updates['custom_field'])} field(s)")

            if not dry_run:
                if api.update_test_case(case_id, updates):
                    stats["fixed"] += 1
                    print(f"  [OK] Fixed case {case_code} ({case_id})")
                else:
                    stats["errors"] += 1
                    print(f"  [ERROR] Failed to fix case {case_code} ({case_id})")
            else:
                print(f"  [DRY RUN] Would fix case {case_code} ({case_id})")
                stats["fixed"] += 1
        else:
            if verbose:
                print(f"  [SKIP] Case {case_code} ({case_id}): No HTML tags found")
            stats["skipped"] += 1

    print("\n" + "-" * 60)
    print(f"Summary for project {project_code}:")
    print(f"  Total test cases:     {stats['total']}")
    print(f"  Cases with HTML tags: {stats['has_html']}")
    print(f"  Cases fixed:          {stats['fixed']}")
    print(f"  Cases skipped:        {stats['skipped']}")
    print(f"  Errors:               {stats['errors']}")
    print(f"    description={stats['fields_fixed']['description']}, "
          f"preconditions={stats['fields_fixed']['preconditions']}, "
          f"postconditions={stats['fields_fixed']['postconditions']}, "
          f"steps={stats['fields_fixed']['steps']}, "
          f"custom_fields={stats['fields_fixed']['custom_fields']}")
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Remove HTML tags from all fields in Qase test cases"
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file (default: config.json)",
    )
    parser.add_argument(
        "--token",
        help="Qase API token (overrides config file)",
    )
    parser.add_argument(
        "--project",
        help=(
            "Qase project code (overrides config file). "
            "Use 'all' to run against every project in the workspace."
        ),
    )
    parser.add_argument(
        "--host",
        help="Qase API host (overrides config 'host'; default api.qase.io or from config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without making changes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed information about each case",
    )

    args = parser.parse_args()

    config: Optional[Dict[str, Any]] = None
    api_token: Optional[str] = args.token
    project_code: Optional[str] = args.project

    try:
        config = load_config(args.config)
        api_token = api_token or config.get("api_token")
        project_code = project_code or config.get("project_code")
    except (FileNotFoundError, ValueError) as e:
        if not api_token or not project_code:
            parser.error(f"Error loading config: {e}")

    if not api_token or not project_code:
        parser.error("API token and project code are required (via config or CLI)")

    base_url = resolve_qase_base_url(args.host, config, args.config)

    if str(project_code).strip().lower() == "all":
        codes = list_workspace_project_codes(api_token, base_url)
        if not codes:
            parser.error("No projects returned by the API.")
        if not confirm_run_all_projects(
            codes, action="remove HTML tags from", dry_run=args.dry_run
        ):
            print("Aborted.")
            return

        totals = {"total": 0, "has_html": 0, "fixed": 0, "errors": 0, "skipped": 0}
        field_totals = {
            "description": 0, "preconditions": 0, "postconditions": 0,
            "steps": 0, "custom_fields": 0,
        }
        for code in codes:
            s = _run_for_project(
                api_token, code, base_url, args.dry_run, args.verbose
            )
            for k in totals:
                totals[k] += int(s.get(k, 0))
            for k in field_totals:
                field_totals[k] += int(s["fields_fixed"].get(k, 0))

        print("\n" + "=" * 60)
        print(f"Workspace-wide summary ({len(codes)} projects)")
        print("=" * 60)
        print(f"  Total test cases:     {totals['total']}")
        print(f"  Cases with HTML tags: {totals['has_html']}")
        print(f"  Cases fixed:          {totals['fixed']}")
        print(f"  Cases skipped:        {totals['skipped']}")
        print(f"  Errors:               {totals['errors']}")
        print("\nFields fixed:")
        for k, v in field_totals.items():
            print(f"  {k}: {v}")
        print("=" * 60)
    else:
        _run_for_project(
            api_token,
            str(project_code).strip(),
            base_url,
            args.dry_run,
            args.verbose,
        )


if __name__ == "__main__":
    main()
