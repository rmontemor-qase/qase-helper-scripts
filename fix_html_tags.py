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

from qase_api import QaseAPI, resolve_qase_base_url


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


def main():
    parser = argparse.ArgumentParser(
        description="Remove HTML tags from all fields in Qase test cases"
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file (default: config.json)"
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
        help="Show detailed information about each case"
    )

    args = parser.parse_args()

    # Load config
    config: Optional[Dict[str, Any]] = None
    try:
        config = load_config(args.config)
        api_token = config.get("api_token")
        project_code = config.get("project_code")
    except (FileNotFoundError, ValueError) as e:
        parser.error(f"Error loading config: {e}")

    if not api_token or not project_code:
        parser.error("API token and project code are required in config file")

    base_url = resolve_qase_base_url(args.host, config, args.config)

    # Initialize API
    api = QaseAPI(api_token, project_code, base_url)

    # Fetch all test cases
    print(f"\nFetching test cases from project '{project_code}'...")
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
            "custom_fields": 0
        }
    }

    print(f"\nAnalyzing {stats['total']} test cases for HTML tags in all fields...")

    for test_case in test_cases:
        case_id = test_case.get("id")
        case_code = test_case.get("code", "")
        title = test_case.get("title", "Untitled")
        
        # Analyze test case for HTML tags
        updates = analyze_test_case(test_case)
        
        if updates:
            stats["has_html"] += 1
            
            # Count which fields were fixed
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
            
            if args.verbose:
                print(f"\n  Case {case_code} ({case_id}): '{title}'")
                print(f"    Fields to fix: {list(updates.keys())}")
                if "custom_field" in updates:
                    print(f"    Custom fields: {len(updates['custom_field'])} field(s)")

            if not args.dry_run:
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
            if args.verbose:
                print(f"  [SKIP] Case {case_code} ({case_id}): No HTML tags found")
            stats["skipped"] += 1

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total test cases: {stats['total']}")
    print(f"  Cases with HTML tags: {stats['has_html']}")
    print(f"  Cases fixed: {stats['fixed']}")
    print(f"  Cases skipped: {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")
    print("\nFields fixed:")
    print(f"  Description: {stats['fields_fixed']['description']}")
    print(f"  Preconditions: {stats['fields_fixed']['preconditions']}")
    print(f"  Postconditions: {stats['fields_fixed']['postconditions']}")
    print(f"  Steps: {stats['fields_fixed']['steps']}")
    print(f"  Custom fields: {stats['fields_fixed']['custom_fields']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
