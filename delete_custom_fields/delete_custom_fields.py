#!/usr/bin/env python3
"""
Delete All Custom Fields Script

This script deletes all custom fields from a Qase workspace.
It reads the API token from config.json and removes all custom fields found.
"""

import json
import os
import sys
import requests
from typing import Dict, List, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qase_api import resolve_qase_base_url


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
            f"Please create it with 'api_token' field."
        )

    with open(config_path, 'r') as f:
        config = json.load(f)

    if "api_token" not in config:
        raise ValueError("Config file must contain 'api_token' field")

    if not config.get("api_token"):
        raise ValueError("API token is empty in config file")

    return config


def get_all_custom_fields(api_token: str, base_url: str) -> List[Dict[str, Any]]:
    """
    Fetch all custom fields from the workspace using pagination.

    Args:
        api_token: Qase API token

    Returns:
        List of custom field dictionaries
    """
    all_fields = []
    offset = 0
    limit = 100
    headers = {
        "Token": api_token,
        "accept": "application/json"
    }

    print("Fetching custom fields from workspace...")

    while True:
        url = f"{base_url}/custom_field"
        params = {"limit": limit, "offset": offset}

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            if not data.get("status"):
                print(f"Error: API returned status false")
                break

            result = data.get("result", {})
            entities = result.get("entities", [])
            total = result.get("total", 0)
            count = result.get("count", 0)

            all_fields.extend(entities)
            print(f"Fetched {len(entities)} custom fields (offset: {offset}, total: {total})")

            # Check if we've fetched all fields
            if offset + count >= total or len(entities) == 0:
                break

            offset += count

        except requests.exceptions.RequestException as e:
            print(f"Error fetching custom fields: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            break

    print(f"Total custom fields fetched: {len(all_fields)}")
    return all_fields


def delete_custom_field(api_token: str, field_id: int, base_url: str) -> bool:
    """
    Delete a custom field by ID.

    Args:
        api_token: Qase API token
        field_id: ID of the custom field to delete

    Returns:
        True if deletion was successful, False otherwise
    """
    url = f"{base_url}/custom_field/{field_id}"
    headers = {
        "Token": api_token,
        "accept": "application/json"
    }

    try:
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error deleting custom field {field_id}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False


def main():
    """Main entry point."""
    print("=" * 60)
    print("Delete All Custom Fields")
    print("=" * 60)
    print()

    # Load config
    try:
        config = load_config()
        api_token = config.get("api_token")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    base_url = resolve_qase_base_url(None, config, "config.json")

    # Get all custom fields
    custom_fields = get_all_custom_fields(api_token, base_url)

    if not custom_fields:
        print("\nNo custom fields found. Nothing to delete.")
        return

    print(f"\nFound {len(custom_fields)} custom field(s) to delete:")
    for field in custom_fields:
        field_id = field.get("id")
        field_title = field.get("title", "Unknown")
        print(f"  - ID: {field_id}, Title: {field_title}")

    # Confirm deletion
    print("\n" + "=" * 60)
    response = input(f"Are you sure you want to delete all {len(custom_fields)} custom field(s)? (yes/no): ")
    if response.lower() != "yes":
        print("Deletion cancelled.")
        return

    print("\nDeleting custom fields...")
    print()

    # Delete each custom field
    deleted_count = 0
    failed_count = 0

    for field in custom_fields:
        field_id = field.get("id")
        field_title = field.get("title", "Unknown")

        print(f"Deleting custom field ID {field_id} ('{field_title}')...", end=" ")
        if delete_custom_field(api_token, field_id, base_url):
            print("✓ Success")
            deleted_count += 1
        else:
            print("✗ Failed")
            failed_count += 1

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total custom fields: {len(custom_fields)}")
    print(f"  Successfully deleted: {deleted_count}")
    print(f"  Failed: {failed_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
