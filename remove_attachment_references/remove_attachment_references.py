#!/usr/bin/env python3
"""
Remove Attachment References from Test Cases

This script removes attachment reference patterns like:
[![attachment](https://.../attachment/HASH/attachment)](index.php?/attachments/get/ID)

from all text fields in Qase test cases, including description, preconditions,
postconditions, steps, and custom fields.
"""

import json
import os
import argparse
import re
import requests
from typing import Dict, Optional, Any, List, Tuple

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qase_api import (
    QaseAPI,
    resolve_qase_base_url,
    list_workspace_project_codes,
    confirm_run_all_projects,
)


def remove_attachment_references(text: str) -> str:
    """
    Remove attachment reference patterns from text.
    
    Patterns:
    1. [![attachment](URL)](index.php?/attachments/get/ID)
    2. ![attachment](URL)
    
    Args:
        text: Text that may contain attachment references
        
    Returns:
        Text with attachment references removed
    """
    if not text:
        return text
    
    # Pattern 1: [![attachment](...)](index.php?/attachments/get/...)
    # Matches the full markdown link structure with attachment ID
    pattern1 = r'\[!\[attachment\]\([^\)]+\)\]\(index\.php\?/attachments/get/\d+\)'
    
    # Pattern 2: ![attachment](URL)
    # Matches simple markdown image links with "attachment" as alt text
    # The URL typically contains /attachment/ in the path
    pattern2 = r'!\[attachment\]\([^\)]+\)'
    
    # Remove all matches (apply both patterns)
    cleaned_text = re.sub(pattern1, '', text)
    cleaned_text = re.sub(pattern2, '', cleaned_text)
    
    # Clean up any extra whitespace or newlines left behind
    # Replace multiple spaces with single space (but preserve newlines)
    lines = cleaned_text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Clean up multiple spaces within each line
        cleaned_line = re.sub(r' +', ' ', line)
        cleaned_lines.append(cleaned_line)
    cleaned_text = '\n'.join(cleaned_lines)
    
    # Replace multiple newlines with at most 2 newlines
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    
    return cleaned_text.strip()


def ensure_step_has_action(step: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure a step has a non-empty action field.
    If action is empty or None, set it to ".".
    
    Args:
        step: Step dictionary
        
    Returns:
        Step dictionary with guaranteed action field
    """
    fixed_step = step.copy()
    
    # Ensure action field exists and is not empty
    if not fixed_step.get("action") or not fixed_step["action"].strip():
        fixed_step["action"] = "."
    
    # Recursively fix nested steps
    if fixed_step.get("steps"):
        fixed_nested_steps = []
        for nested_step in fixed_step["steps"]:
            fixed_nested_steps.append(ensure_step_has_action(nested_step))
        fixed_step["steps"] = fixed_nested_steps
    
    return fixed_step


def analyze_test_case(test_case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a test case and return fields that need attachment reference removal.
    
    Args:
        test_case: Test case dictionary from the API
        
    Returns:
        Dictionary with only the fields that need fixing
    """
    updates = {}
    
    # Check description
    description = test_case.get("description")
    if description:
        cleaned_description = remove_attachment_references(description)
        if description != cleaned_description:
            updates["description"] = cleaned_description
    
    # Check preconditions
    preconditions = test_case.get("preconditions")
    if preconditions:
        cleaned_preconditions = remove_attachment_references(preconditions)
        if preconditions != cleaned_preconditions:
            updates["preconditions"] = cleaned_preconditions
    
    # Check postconditions
    postconditions = test_case.get("postconditions")
    if postconditions:
        cleaned_postconditions = remove_attachment_references(postconditions)
        if postconditions != cleaned_postconditions:
            updates["postconditions"] = cleaned_postconditions
    
    # Check steps
    steps = test_case.get("steps", [])
    if steps:
        fixed_steps = []
        steps_need_update = False
        
        def fix_step(step: Dict[str, Any]) -> tuple:
            """Recursively fix a step and its nested steps."""
            fixed_step = step.copy()
            step_changed = False
            
            # Fix action
            if step.get("action"):
                cleaned_action = remove_attachment_references(step["action"])
                if step["action"] != cleaned_action:
                    fixed_step["action"] = cleaned_action
                    step_changed = True
            
            # Ensure action is not empty after cleaning
            if not fixed_step.get("action") or not fixed_step["action"].strip():
                fixed_step["action"] = "."
                step_changed = True
            
            # Fix expected_result
            if step.get("expected_result"):
                cleaned_expected = remove_attachment_references(step["expected_result"])
                if step["expected_result"] != cleaned_expected:
                    fixed_step["expected_result"] = cleaned_expected
                    step_changed = True
            
            # Fix data
            if step.get("data"):
                cleaned_data = remove_attachment_references(step["data"])
                if step["data"] != cleaned_data:
                    fixed_step["data"] = cleaned_data
                    step_changed = True
            
            # Fix nested steps recursively
            if step.get("steps"):
                fixed_nested_steps = []
                for nested_step in step["steps"]:
                    fixed_nested, nested_changed = fix_step(nested_step)
                    fixed_nested_steps.append(fixed_nested)
                    if nested_changed:
                        step_changed = True
                fixed_step["steps"] = fixed_nested_steps
            
            return fixed_step, step_changed
        
        for step in steps:
            fixed_step, step_changed = fix_step(step)
            fixed_steps.append(fixed_step)
            if step_changed:
                steps_need_update = True
        
        if steps_need_update:
            # Ensure all steps have non-empty action fields before sending
            final_fixed_steps = []
            for step in fixed_steps:
                final_fixed_steps.append(ensure_step_has_action(step))
            updates["steps"] = final_fixed_steps
    
    # Check custom_fields
    # Note: API expects "custom_field" (singular) as an object with field IDs as keys
    custom_fields = test_case.get("custom_fields", [])
    if custom_fields:
        custom_field_updates = {}
        custom_fields_need_update = False
        
        for field in custom_fields:
            field_id = field.get("id")
            value = field.get("value")
            if value:
                cleaned_value = remove_attachment_references(value)
                if value != cleaned_value and field_id is not None:
                    # API expects field ID as string key
                    custom_field_updates[str(field_id)] = cleaned_value
                    custom_fields_need_update = True
        
        if custom_fields_need_update:
            updates["custom_field"] = custom_field_updates
    
    return updates


def update_test_case_with_retry(api: QaseAPI, case_id: int, updates: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Update a test case with retry logic for empty action fields.
    
    Args:
        api: QaseAPI instance
        case_id: Test case ID
        updates: Dictionary containing fields to update
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    # First attempt
    try:
        url = f"{api.base_url}/case/{api.project_code}/{case_id}"
        response = requests.patch(url, headers=api.headers, json=updates)
        response.raise_for_status()
        return True, "Success"
    except requests.exceptions.HTTPError as e:
        # Check if error is about missing action field
        if e.response and e.response.status_code == 422:
            try:
                error_data = e.response.json()
                errors = error_data.get("errors", {})
                
                # Check if any step has "Action field is required" error
                has_action_error = False
                for key, value in errors.items():
                    if isinstance(value, list) and any("Action field is required" in str(err) for err in value):
                        has_action_error = True
                        break
                    elif isinstance(value, str) and "Action field is required" in value:
                        has_action_error = True
                        break
                
                if has_action_error and "steps" in updates:
                    # Fix all steps to ensure they have non-empty action fields
                    fixed_steps = []
                    for step in updates["steps"]:
                        fixed_step = ensure_step_has_action(step)
                        fixed_steps.append(fixed_step)
                    updates["steps"] = fixed_steps
                    
                    # Retry with fixed steps
                    try:
                        response = requests.patch(url, headers=api.headers, json=updates)
                        response.raise_for_status()
                        return True, "Success (patched empty actions)"
                    except requests.exceptions.RequestException as retry_e:
                        error_msg = f"Failed after patching: {retry_e}"
                        if hasattr(retry_e, 'response') and retry_e.response is not None:
                            error_msg += f" - {retry_e.response.text}"
                        return False, error_msg
            except (ValueError, KeyError):
                pass
        
        # Return original error
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f" - {e.response.text}"
        return False, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f" - {e.response.text}"
        return False, error_msg


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Load configuration from a JSON file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file '{config_path}' not found.")

    with open(config_path, 'r') as f:
        config = json.load(f)

    if "api_token" not in config:
        raise ValueError("Config file must contain 'api_token' field")

    return config


def _run_for_project(
    api_token: str,
    project_code: str,
    base_url: str,
    dry_run: bool,
    verbose: bool,
) -> Dict[str, Any]:
    """Run the attachment-reference cleanup for a single project."""
    api = QaseAPI(api_token, project_code, base_url)

    print("\n" + "=" * 60)
    print("Remove Attachment References from Test Cases")
    print("=" * 60)
    print(f"Project: {project_code}")
    if dry_run:
        print("DRY RUN MODE - No changes will be made")
    if verbose:
        print("VERBOSE MODE - Showing detailed information")
    print()

    test_cases = api.get_all_test_cases()

    if not test_cases:
        print("No test cases found.")
        return {
            "total": 0, "has_references": 0, "fixed": 0, "errors": 0, "skipped": 0,
            "fields_fixed": {
                "description": 0, "preconditions": 0, "postconditions": 0,
                "steps": 0, "custom_fields": 0,
            },
        }

    stats = {
        "total": len(test_cases),
        "has_references": 0,
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

    print(f"\nAnalyzing {stats['total']} test cases for attachment references...")

    processed = 0
    for idx, test_case in enumerate(test_cases, 1):
        case_id = test_case.get("id")
        case_code = test_case.get("code", f"C{case_id}")
        title = test_case.get("title", "Untitled")
        
        # Calculate and display progress
        progress_pct = (idx / stats['total']) * 100
        progress_bar_length = 40
        filled = int(progress_bar_length * idx // stats['total'])
        bar = '=' * filled + '>' + '-' * (progress_bar_length - filled - 1)
        
        # Analyze test case for attachment references
        updates = analyze_test_case(test_case)
        
        if updates:
            stats["has_references"] += 1
            
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
            
            if verbose:
                print(f"\n  Case {case_code} ({case_id}): '{title}'")
                print(f"    Fields to fix: {list(updates.keys())}")
                if "custom_field" in updates:
                    print(f"    Custom fields: {len(updates['custom_field'])} field(s)")

            if not dry_run:
                success, message = update_test_case_with_retry(api, case_id, updates)
                if success:
                    stats["fixed"] += 1
                    processed += 1
                    if "patched empty actions" in message:
                        print(f"  [OK] Fixed case {case_code} ({case_id}) - patched empty actions")
                    else:
                        print(f"  [OK] Fixed case {case_code} ({case_id})")
                else:
                    stats["errors"] += 1
                    processed += 1
                    if verbose:
                        print(f"  [ERROR] Failed to fix case {case_code} ({case_id}): {message}")
                    else:
                        print(f"  [ERROR] Failed to fix case {case_code} ({case_id})")
            else:
                print(f"  [DRY RUN] Would fix case {case_code} ({case_id})")
                stats["fixed"] += 1
                processed += 1

            print(f"\rProgress: [{bar}] {progress_pct:.1f}% ({idx}/{stats['total']}) | Fixed: {stats['fixed']}, Errors: {stats['errors']}, Skipped: {stats['skipped']}", end="", flush=True)
        else:
            processed += 1
            stats["skipped"] += 1
            if verbose:
                print(f"  [SKIP] Case {case_code} ({case_id}): No attachment references found")
            print(f"\rProgress: [{bar}] {progress_pct:.1f}% ({idx}/{stats['total']}) | Fixed: {stats['fixed']}, Errors: {stats['errors']}, Skipped: {stats['skipped']}", end="", flush=True)

    print()
    final_bar = '=' * progress_bar_length
    final_pct = 100.0
    print(f"Progress: [{final_bar}] {final_pct:.1f}% ({stats['total']}/{stats['total']}) | Fixed: {stats['fixed']}, Errors: {stats['errors']}, Skipped: {stats['skipped']}")

    print("\n" + "-" * 60)
    print(f"Summary for project {project_code}:")
    print(f"  Total test cases: {stats['total']}")
    print(f"  Cases with attachment references: {stats['has_references']}")
    print(f"  Cases fixed: {stats['fixed']}")
    print(f"  Cases skipped: {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Remove attachment references from Qase test cases"
    )
    parser.add_argument(
        "--config", default="config.json",
        help="Path to config file (default: config.json)",
    )
    parser.add_argument(
        "--project",
        help=(
            "Qase project code (overrides config file). "
            "Use 'all' to run against every project in the workspace."
        ),
    )
    parser.add_argument("--token", help="Qase API token (overrides config file)")
    parser.add_argument(
        "--host",
        help="Qase API host (overrides config 'host'; default api.qase.io or from config)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Perform a dry run without making changes",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed information about each test case",
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

    if not api_token:
        parser.error("API token is required (provide via --token or config file)")
    if not project_code:
        parser.error("Project code is required (provide via --project or config file)")

    base_url = resolve_qase_base_url(args.host, config, args.config)

    if str(project_code).strip().lower() == "all":
        codes = list_workspace_project_codes(api_token, base_url)
        if not codes:
            parser.error("No projects returned by the API.")
        if not confirm_run_all_projects(
            codes, action="remove attachment references in", dry_run=args.dry_run
        ):
            print("Aborted.")
            return

        totals = {"total": 0, "has_references": 0, "fixed": 0, "errors": 0, "skipped": 0}
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
        print(f"  Total test cases:                 {totals['total']}")
        print(f"  Cases with attachment references: {totals['has_references']}")
        print(f"  Cases fixed:                      {totals['fixed']}")
        print(f"  Cases skipped:                    {totals['skipped']}")
        print(f"  Errors:                           {totals['errors']}")
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
