#!/usr/bin/env python3
"""
Delete Attachments by Size Script

This script deletes all attachments from a Qase workspace that match a specific size.
It reads the API token from config.json and uses multiple workers for parallel deletion.
"""

import json
import os
import sys
import requests
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qase_api import resolve_qase_base_url
from threading import Lock


# Thread-safe counter for progress tracking
class ProgressCounter:
    def __init__(self):
        self.lock = Lock()
        self.deleted = 0
        self.failed = 0
        self.total = 0

    def increment_deleted(self):
        with self.lock:
            self.deleted += 1

    def increment_failed(self):
        with self.lock:
            self.failed += 1

    def get_progress(self):
        with self.lock:
            return self.deleted, self.failed, self.total


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


def get_all_attachments(api_token: str, base_url: str) -> List[Dict[str, Any]]:
    """
    Fetch all attachments from the workspace using pagination.

    Args:
        api_token: Qase API token

    Returns:
        List of attachment dictionaries
    """
    all_attachments = []
    offset = 0
    limit = 100
    headers = {
        "Token": api_token,
        "accept": "application/json"
    }

    print("Fetching attachments from workspace...")

    while True:
        url = f"{base_url}/attachment"
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

            all_attachments.extend(entities)
            print(f"Fetched {len(entities)} attachments (offset: {offset}, total: {total})")

            # Check if we've fetched all attachments
            if offset + count >= total or len(entities) == 0:
                break

            offset += count

        except requests.exceptions.RequestException as e:
            print(f"Error fetching attachments: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            break

    print(f"Total attachments fetched: {len(all_attachments)}")
    return all_attachments


def delete_attachment(api_token: str, attachment_hash: str, base_url: str) -> bool:
    """
    Delete an attachment by hash.

    Args:
        api_token: Qase API token
        attachment_hash: Hash of the attachment to delete

    Returns:
        True if deletion was successful, False otherwise
    """
    url = f"{base_url}/attachment/{attachment_hash}"
    headers = {
        "Token": api_token,
        "accept": "application/json"
    }

    try:
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"\nError deleting attachment {attachment_hash}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False


def delete_attachment_worker(args: tuple) -> tuple:
    """
    Worker function for deleting a single attachment.
    
    Args:
        args: Tuple of (api_token, base_url, attachment_hash, attachment_info, counter)
    
    Returns:
        Tuple of (attachment_hash, success)
    """
    api_token, base_url, attachment_hash, attachment_info, counter = args
    success = delete_attachment(api_token, attachment_hash, base_url)
    
    if success:
        counter.increment_deleted()
    else:
        counter.increment_failed()
    
    return attachment_hash, success


def main():
    """Main entry point."""
    print("=" * 60)
    print("Delete Attachments by Size")
    print("=" * 60)
    print()

    # Configuration
    TARGET_SIZE = 157010
    NUM_WORKERS = 10

    # Load config
    try:
        config = load_config()
        api_token = config.get("api_token")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    base_url = resolve_qase_base_url(None, config, "config.json")

    # Get all attachments
    all_attachments = get_all_attachments(api_token, base_url)

    if not all_attachments:
        print("\nNo attachments found.")
        return

    # Filter attachments by size
    matching_attachments = [
        att for att in all_attachments
        if att.get("size") == TARGET_SIZE
    ]

    if not matching_attachments:
        print(f"\nNo attachments found with size {TARGET_SIZE}.")
        print(f"Total attachments checked: {len(all_attachments)}")
        return

    print(f"\nFound {len(matching_attachments)} attachment(s) with size {TARGET_SIZE}:")
    for att in matching_attachments[:10]:  # Show first 10
        att_hash = att.get("hash")
        att_file = att.get("file", "Unknown")
        att_size = att.get("size")
        print(f"  - Hash: {att_hash[:16]}..., File: {att_file}, Size: {att_size}")
    
    if len(matching_attachments) > 10:
        print(f"  ... and {len(matching_attachments) - 10} more")

    # Confirm deletion
    print("\n" + "=" * 60)
    response = input(f"Are you sure you want to delete all {len(matching_attachments)} attachment(s) with size {TARGET_SIZE}? (yes/no): ")
    if response.lower() != "yes":
        print("Deletion cancelled.")
        return

    print(f"\nDeleting attachments using {NUM_WORKERS} workers...")
    print()

    # Initialize progress counter
    counter = ProgressCounter()
    counter.total = len(matching_attachments)

    # Prepare arguments for workers
    worker_args = [
        (api_token, base_url, att.get("hash"), att, counter)
        for att in matching_attachments
    ]

    # Delete attachments in parallel
    deleted_count = 0
    failed_count = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Submit all deletion tasks
        future_to_hash = {
            executor.submit(delete_attachment_worker, args): args[2]
            for args in worker_args
        }

        # Process completed tasks and show progress
        for future in as_completed(future_to_hash):
            completed += 1
            attachment_hash, success = future.result()
            
            deleted, failed, total = counter.get_progress()
            progress_pct = (completed / total) * 100
            
            # Show progress every 10 completions or at the end
            if completed % 10 == 0 or completed == total:
                print(f"\rProgress: {completed}/{total} ({progress_pct:.1f}%) | "
                      f"Deleted: {deleted}, Failed: {failed}", end="", flush=True)

    print()  # New line after progress

    # Final summary
    deleted, failed, total = counter.get_progress()
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total attachments checked: {len(all_attachments)}")
    print(f"  Attachments with size {TARGET_SIZE}: {len(matching_attachments)}")
    print(f"  Successfully deleted: {deleted}")
    print(f"  Failed: {failed}")
    print(f"  Workers used: {NUM_WORKERS}")
    print("=" * 60)


if __name__ == "__main__":
    main()
