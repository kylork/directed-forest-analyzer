#!/usr/bin/env python3
"""
Benchmark: Tantivy vs FTS5 for ChatGPT conversation indexing and search.
"""

import json
import time
import tempfile
import shutil
from pathlib import Path

# Test data
JSON_FILE = Path(r"N:\claude-code\directed-tree-merger\Robin_merged.json")


def extract_messages(conversations: list) -> list[dict]:
    """Extract all messages from conversations for indexing."""
    messages = []
    for conv in conversations:
        conv_id = conv.get('conversation_id', '')
        title = conv.get('title', 'Untitled')
        mapping = conv.get('mapping', {})

        for node_id, node in mapping.items():
            msg = node.get('message')
            if msg and msg.get('content'):
                content = msg['content']
                if content.get('content_type') == 'text':
                    parts = content.get('parts', [])
                    text = ' '.join(str(p) for p in parts if p)
                    if text.strip():
                        role = msg.get('author', {}).get('role', 'unknown')
                        messages.append({
                            'node_id': node_id,
                            'conv_id': conv_id,
                            'title': title,
                            'role': role,
                            'text': text
                        })
    return messages


def benchmark_tantivy(messages: list[dict], queries: list[str]) -> dict:
    """Benchmark Tantivy indexing and search."""
    import tantivy

    results = {'engine': 'Tantivy'}

    # Create temp directory for index
    index_dir = tempfile.mkdtemp(prefix='tantivy_')

    try:
        # Define schema
        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("node_id", stored=True)
        schema_builder.add_text_field("conv_id", stored=True)
        schema_builder.add_text_field("title", stored=True)
        schema_builder.add_text_field("role", stored=True)
        schema_builder.add_text_field("text", stored=True)
        schema = schema_builder.build()

        # Create index
        index = tantivy.Index(schema, path=index_dir)

        # Index messages
        start = time.perf_counter()
        writer = index.writer()
        for msg in messages:
            writer.add_document(tantivy.Document(
                node_id=msg['node_id'],
                conv_id=msg['conv_id'],
                title=msg['title'],
                role=msg['role'],
                text=msg['text']
            ))
        writer.commit()
        index.reload()
        results['index_time'] = time.perf_counter() - start

        # Search
        searcher = index.searcher()

        search_times = []
        for q in queries:
            start = time.perf_counter()
            query = index.parse_query(q, ["text", "title"])
            hits = searcher.search(query, 100).hits
            search_times.append(time.perf_counter() - start)

        results['search_times'] = search_times
        results['avg_search_ms'] = sum(search_times) / len(search_times) * 1000

    finally:
        shutil.rmtree(index_dir, ignore_errors=True)

    return results


def benchmark_fts5(messages: list[dict], queries: list[str]) -> dict:
    """Benchmark SQLite FTS5 indexing and search."""
    import sqlite3

    results = {'engine': 'FTS5'}

    # Create temp database
    db_file = tempfile.mktemp(suffix='.db', prefix='fts5_')

    try:
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()

        # Create FTS5 table
        cur.execute('''
            CREATE VIRTUAL TABLE messages USING fts5(
                node_id, conv_id, title, role, text
            )
        ''')

        # Index messages
        start = time.perf_counter()
        cur.executemany(
            'INSERT INTO messages (node_id, conv_id, title, role, text) VALUES (?, ?, ?, ?, ?)',
            [(m['node_id'], m['conv_id'], m['title'], m['role'], m['text']) for m in messages]
        )
        conn.commit()
        results['index_time'] = time.perf_counter() - start

        # Search
        search_times = []
        for q in queries:
            start = time.perf_counter()
            # FTS5 query - search in text and title
            cur.execute(
                'SELECT node_id, conv_id, title, role FROM messages WHERE messages MATCH ? LIMIT 100',
                (q,)
            )
            _ = cur.fetchall()
            search_times.append(time.perf_counter() - start)

        results['search_times'] = search_times
        results['avg_search_ms'] = sum(search_times) / len(search_times) * 1000

        conn.close()

    finally:
        Path(db_file).unlink(missing_ok=True)

    return results


def main():
    print(f"Loading {JSON_FILE}...")
    start = time.perf_counter()
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        conversations = json.load(f)
    load_time = time.perf_counter() - start
    print(f"Loaded {len(conversations)} conversations in {load_time:.2f}s")

    print("Extracting messages...")
    start = time.perf_counter()
    messages = extract_messages(conversations)
    extract_time = time.perf_counter() - start
    print(f"Extracted {len(messages)} messages in {extract_time:.2f}s")

    # Test queries
    queries = [
        "hello",
        "love",
        "python",
        "remember",
        "conversation",
    ]

    print("\n" + "=" * 50)
    print("BENCHMARK: Tantivy vs FTS5")
    print("=" * 50)
    print(f"Messages to index: {len(messages)}")
    print(f"Test queries: {queries}")
    print()

    # Run benchmarks
    print("Running Tantivy benchmark...")
    tantivy_results = benchmark_tantivy(messages, queries)

    print("Running FTS5 benchmark...")
    fts5_results = benchmark_fts5(messages, queries)

    # Results
    print("\n" + "-" * 50)
    print("INDEXING TIME:")
    print(f"  Tantivy: {tantivy_results['index_time']:.3f}s")
    print(f"  FTS5:    {fts5_results['index_time']:.3f}s")
    print(f"  Ratio:   Tantivy is {fts5_results['index_time']/tantivy_results['index_time']:.1f}x faster")

    print("\nSEARCH TIME (avg):")
    print(f"  Tantivy: {tantivy_results['avg_search_ms']:.2f}ms")
    print(f"  FTS5:    {fts5_results['avg_search_ms']:.2f}ms")
    print(f"  Ratio:   Tantivy is {fts5_results['avg_search_ms']/tantivy_results['avg_search_ms']:.1f}x faster")

    print("\nSEARCH TIME (per query):")
    for i, q in enumerate(queries):
        t_ms = tantivy_results['search_times'][i] * 1000
        f_ms = fts5_results['search_times'][i] * 1000
        print(f"  '{q}': Tantivy {t_ms:.2f}ms, FTS5 {f_ms:.2f}ms")

    print("\n" + "=" * 50)


if __name__ == '__main__':
    main()
