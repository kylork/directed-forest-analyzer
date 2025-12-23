#!/usr/bin/env python3
"""
Directed Forest Merger

A tool for comparing and merging ChatGPT conversation exports.
Handles the "directed forest" structure where each conversation is a tree
and the export file contains multiple disconnected trees.
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Any


def load_conversations(filepath: Path) -> dict[str, dict[str, Any]]:
    """Load conversations from a JSON file, indexed by conversation_id."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {conv['conversation_id']: conv for conv in data}


def get_conversation_size(conv: dict[str, Any]) -> int:
    """Get the number of nodes in a conversation's mapping (tree size)."""
    return len(conv.get('mapping', {}))


def compare_forests(past: dict[str, dict], present: dict[str, dict]) -> dict:
    """
    Compare two conversation forests.

    Returns a dict with:
    - missing_in_present: conversations in PAST but not in PRESENT
    - stats: summary statistics
    """
    past_ids = set(past.keys())
    present_ids = set(present.keys())

    missing_in_present = past_ids - present_ids
    missing_in_past = present_ids - past_ids

    return {
        'missing_in_present': [
            {
                'conversation_id': cid,
                'title': past[cid].get('title', 'Untitled'),
                'nodes': get_conversation_size(past[cid])
            }
            for cid in missing_in_present
        ],
        'missing_in_past': len(missing_in_past),
        'stats': {
            'past_total': len(past),
            'present_total': len(present),
            'common': len(past_ids & present_ids),
            'missing_conversations': len(missing_in_present)
        }
    }


def merge_forests(past: dict[str, dict], present: dict[str, dict]) -> list[dict]:
    """
    Merge two forests, preferring the more complete version of each conversation.

    For each conversation:
    - If only in one file, include it
    - If in both, use the one with more nodes (more complete)
    """
    merged = {}
    all_ids = set(past.keys()) | set(present.keys())

    for conv_id in all_ids:
        past_conv = past.get(conv_id)
        present_conv = present.get(conv_id)

        if past_conv is None:
            merged[conv_id] = present_conv
        elif present_conv is None:
            merged[conv_id] = past_conv
        else:
            # Both exist - use the larger one
            past_size = get_conversation_size(past_conv)
            present_size = get_conversation_size(present_conv)
            merged[conv_id] = past_conv if past_size >= present_size else present_conv

    # Return as list, sorted by update_time (most recent first)
    result = list(merged.values())
    result.sort(key=lambda x: x.get('update_time', 0), reverse=True)
    return result


def print_report(comparison: dict, past_file: str, present_file: str):
    """Print a human-readable comparison report."""
    stats = comparison['stats']

    print("=" * 60)
    print("DIRECTED FOREST COMPARISON REPORT")
    print("=" * 60)
    print(f"\nPAST file:    {past_file}")
    print(f"PRESENT file: {present_file}")
    print(f"\n--- Summary ---")
    print(f"PAST conversations:    {stats['past_total']}")
    print(f"PRESENT conversations: {stats['present_total']}")
    print(f"Common conversations:  {stats['common']}")
    print(f"Missing in PRESENT:    {stats['missing_conversations']}")

    if comparison['missing_in_present']:
        print(f"\n--- Missing Conversations (in PAST but not PRESENT) ---")
        for conv in sorted(comparison['missing_in_present'], key=lambda x: x['nodes'], reverse=True):
            print(f"  [{conv['nodes']:4d} nodes] {conv['title'][:50]}")
            print(f"             ID: {conv['conversation_id']}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Compare and merge ChatGPT conversation exports (directed forests)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare two files and show diff report
  python forest_merger.py compare past.json present.json

  # Merge two files into a new file
  python forest_merger.py merge past.json present.json -o merged.json

  # Compare and save report to JSON
  python forest_merger.py compare past.json present.json --json report.json
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Compare command
    compare_parser = subparsers.add_parser('compare', help='Compare two conversation files')
    compare_parser.add_argument('past', help='The older/past file (PAST)')
    compare_parser.add_argument('present', help='The newer/present file (PRESENT)')
    compare_parser.add_argument('--json', metavar='FILE', help='Save comparison report to JSON file')

    # Merge command
    merge_parser = subparsers.add_parser('merge', help='Merge two conversation files')
    merge_parser.add_argument('past', help='The older/past file (PAST)')
    merge_parser.add_argument('present', help='The newer/present file (PRESENT)')
    merge_parser.add_argument('-o', '--output', required=True, help='Output file for merged conversations')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load files
    print(f"Loading {args.past}...")
    past = load_conversations(Path(args.past))
    print(f"Loading {args.present}...")
    present = load_conversations(Path(args.present))

    if args.command == 'compare':
        comparison = compare_forests(past, present)
        print_report(comparison, args.past, args.present)

        if args.json:
            with open(args.json, 'w', encoding='utf-8') as f:
                json.dump(comparison, f, indent=2)
            print(f"\nDetailed report saved to: {args.json}")

    elif args.command == 'merge':
        print("Merging forests...")
        merged = merge_forests(past, present)

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False)

        print(f"Merged {len(merged)} conversations to: {args.output}")


if __name__ == '__main__':
    main()
