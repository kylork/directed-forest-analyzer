#!/usr/bin/env python
"""
Scan a conversations.json file for all content types and report what's handled vs not.
Usage: python scan_content_types.py <path_to_conversations.json>
"""

import json
import sys
from collections import Counter
from pathlib import Path


# Keep this in sync with conversation_analyzer.pyw
HANDLED_CONTENT_TYPES = {'text', 'multimodal_text', 'code'}
HANDLED_PART_TYPES = {'image_asset_pointer', 'audio_asset_pointer'}


def scan_file(filepath: Path) -> dict:
    """Scan a conversations.json and return analysis."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = {
        'file': str(filepath),
        'conversations': len(data),
        'content_types': Counter(),
        'part_types': Counter(),  # nested in multimodal_text
        'author_roles': Counter(),
        'unhandled_samples': {},
        'unhandled_part_samples': {},
    }

    for conv in data:
        mapping = conv.get('mapping', {})
        for node_id, node in mapping.items():
            msg = node.get('message')
            if not msg:
                continue

            # Author roles
            role = msg.get('author', {}).get('role')
            if role:
                results['author_roles'][role] += 1

            content = msg.get('content', {})
            ct = content.get('content_type')
            if not ct:
                continue

            results['content_types'][ct] += 1

            # Save sample of unhandled types
            if ct not in HANDLED_CONTENT_TYPES and ct not in results['unhandled_samples']:
                results['unhandled_samples'][ct] = {
                    'conversation': conv.get('title', 'Untitled'),
                    'keys': list(content.keys()),
                    'sample': _truncate(str(content), 400)
                }

            # Check nested parts in multimodal_text
            if ct == 'multimodal_text':
                parts = content.get('parts', [])
                for part in parts:
                    if isinstance(part, dict):
                        pct = part.get('content_type')
                        if pct:
                            results['part_types'][pct] += 1

                            if pct not in HANDLED_PART_TYPES and pct not in results['unhandled_part_samples']:
                                results['unhandled_part_samples'][pct] = {
                                    'conversation': conv.get('title', 'Untitled'),
                                    'keys': list(part.keys()),
                                    'sample': _truncate(str(part), 400)
                                }

    return results


def _truncate(s: str, length: int) -> str:
    return s[:length] + '...' if len(s) > length else s


def print_report(results: dict):
    """Print a formatted report."""
    print(f"\n{'='*60}")
    print(f"SCAN REPORT: {results['file']}")
    print(f"{'='*60}")
    print(f"Conversations: {results['conversations']}")

    # Content types
    print(f"\n--- Top-level content_types ---")
    print(f"{'Count':>8}  {'Type':<35}  Status")
    print(f"{'-'*8}  {'-'*35}  {'-'*12}")

    for ct, count in results['content_types'].most_common():
        status = "HANDLED" if ct in HANDLED_CONTENT_TYPES else "NOT HANDLED"
        print(f"{count:>8}  {ct:<35}  {status}")

    # Nested part types
    if results['part_types']:
        print(f"\n--- Nested types in multimodal_text parts ---")
        print(f"{'Count':>8}  {'Type':<35}  Status")
        print(f"{'-'*8}  {'-'*35}  {'-'*12}")

        for pct, count in results['part_types'].most_common():
            status = "HANDLED" if pct in HANDLED_PART_TYPES else "NOT HANDLED"
            print(f"{count:>8}  {pct:<35}  {status}")

    # Author roles
    print(f"\n--- Author roles ---")
    for role, count in results['author_roles'].most_common():
        print(f"{count:>8}  {role}")

    # Unhandled samples
    if results['unhandled_samples']:
        print(f"\n--- Samples of unhandled content_types ---")
        for ct, info in results['unhandled_samples'].items():
            print(f"\n[{ct}]")
            print(f"  Found in: {info['conversation']}")
            print(f"  Keys: {info['keys']}")
            print(f"  Sample: {info['sample']}")

    if results['unhandled_part_samples']:
        print(f"\n--- Samples of unhandled part types ---")
        for pct, info in results['unhandled_part_samples'].items():
            print(f"\n[{pct}]")
            print(f"  Found in: {info['conversation']}")
            print(f"  Keys: {info['keys']}")
            print(f"  Sample: {info['sample']}")

    # Summary
    unhandled_count = sum(
        count for ct, count in results['content_types'].items()
        if ct not in HANDLED_CONTENT_TYPES
    )
    total = sum(results['content_types'].values())
    handled_pct = ((total - unhandled_count) / total * 100) if total else 0

    print(f"\n{'='*60}")
    print(f"SUMMARY: {handled_pct:.1f}% of messages handled ({total - unhandled_count}/{total})")
    print(f"{'='*60}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scan_content_types.py <conversations.json>")
        print("\nScans a ChatGPT export file and reports all content types found,")
        print("showing which are handled by conversation_analyzer.pyw and which aren't.")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    print(f"Scanning {filepath}...")
    results = scan_file(filepath)
    print_report(results)


if __name__ == '__main__':
    main()
