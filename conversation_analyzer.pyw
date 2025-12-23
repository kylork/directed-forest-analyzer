#!/usr/bin/env pythonw
"""
ChatGPT Conversation Analyzer

A GUI app for browsing, searching, and exporting ChatGPT conversation exports.
Uses Tantivy for fast full-text search with no stop word filtering.
"""

import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from typing import Any
import tempfile
import shutil
import threading

import tantivy


def get_message_category(msg: dict) -> str:
    """Determine the category of a message for filtering purposes.

    Returns one of: 'user', 'assistant', 'system', 'reasoning', 'tool',
                    'code', 'web_citation', 'error', or 'other'
    """
    if not msg:
        return 'other'

    role = msg.get('author', {}).get('role', '')
    content = msg.get('content', {})
    content_type = content.get('content_type', '')
    metadata = msg.get('metadata', {})

    # Check for reasoning (unified o1/o3/o4)
    if metadata.get('reasoning_status') in ('is_reasoning', 'reasoning_ended'):
        return 'reasoning'
    if content_type == 'thoughts':
        return 'reasoning'
    if content_type == 'reasoning_recap':
        return 'reasoning'

    # Check for specific content types
    if content_type == 'tether_quote':
        return 'web_citation'
    if content_type == 'system_error':
        return 'error'
    if content_type in ('code', 'execution_output'):
        return 'code'

    # Check role
    if role == 'tool':
        return 'tool'
    if role == 'system':
        return 'system'
    if role == 'user':
        return 'user'
    if role == 'assistant':
        return 'assistant'

    return 'other'


def extract_text_from_content(content: dict, include_metadata: bool = False) -> str:
    """Extract text from a message content dict, handling all known types."""
    content_type = content.get('content_type')

    if content_type == 'text':
        parts = content.get('parts', [])
        return ' '.join(str(p) for p in parts if p)

    elif content_type == 'multimodal_text':
        parts = content.get('parts', [])
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                # Could be image, audio, etc. - extract any text field
                if 'text' in part:
                    text_parts.append(part['text'])
                elif part.get('content_type') == 'image_asset_pointer':
                    text_parts.append('[Image]')
                elif part.get('content_type') == 'audio_asset_pointer':
                    text_parts.append('[Audio]')
                elif part.get('content_type') == 'audio_transcription':
                    text_parts.append(part.get('text', '[Audio Transcription]'))
        return ' '.join(text_parts)

    elif content_type == 'code':
        text = content.get('text', '')
        return text if text else '[Code]'

    elif content_type == 'execution_output':
        text = content.get('text', '')
        return f"[Output]: {text}" if text else '[Execution Output]'

    elif content_type == 'thoughts':
        # o3/o4 reasoning thoughts
        thoughts = content.get('thoughts', [])
        if not thoughts:
            return ''
        parts = []
        for thought in thoughts:
            summary = thought.get('summary', '')
            thought_content = thought.get('content', '')
            if summary:
                parts.append(f"[{summary}]")
            if thought_content:
                parts.append(thought_content)
        return '\n'.join(parts) if parts else '[Thinking...]'

    elif content_type == 'reasoning_recap':
        # Just the "Thought for Xs" label
        recap = content.get('content', '')
        return f"[{recap}]" if recap else ''

    elif content_type == 'tether_quote':
        # Web citation
        domain = content.get('domain', '')
        title = content.get('title', '')
        text = content.get('text', '')
        url = content.get('url', '')
        header = f"[Citation: {title or domain or url}]" if (title or domain or url) else '[Citation]'
        return f"{header}\n{text}" if text else header

    elif content_type == 'system_error':
        name = content.get('name', 'Error')
        text = content.get('text', '')
        return f"[Error: {name}] {text}" if text else f"[Error: {name}]"

    elif content_type == 'tether_browsing_display':
        # Usually empty, skip
        return ''

    elif content_type == 'user_editable_context':
        # Custom instructions, skip
        return ''

    return ''


class ConversationIndex:
    """Tantivy-based search index for conversations."""

    def __init__(self, index_dir: str | None = None):
        self.index_dir = index_dir or tempfile.mkdtemp(prefix='conv_index_')
        self.index = None
        self.conversations: dict[str, dict] = {}
        self._setup_index()

    def _setup_index(self):
        """Create the Tantivy index with simple tokenizer (keeps stop words)."""
        # Build schema - use "raw" for stored-only fields, default for searchable
        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("node_id", stored=True)
        schema_builder.add_text_field("conv_id", stored=True)
        schema_builder.add_text_field("title", stored=True)
        schema_builder.add_text_field("role", stored=True)
        schema_builder.add_text_field("text", stored=True)
        schema = schema_builder.build()

        self.index = tantivy.Index(schema, path=self.index_dir)

    def load_conversations(self, filepath: Path, progress_callback=None) -> int:
        """Load conversations from JSON and index them."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.conversations = {conv['conversation_id']: conv for conv in data}

        # Index all messages
        writer = self.index.writer()
        msg_count = 0

        for i, conv in enumerate(data):
            conv_id = conv.get('conversation_id', '')
            title = conv.get('title', 'Untitled')
            mapping = conv.get('mapping', {})

            for node_id, node in mapping.items():
                msg = node.get('message')
                if msg and msg.get('content'):
                    content = msg['content']
                    text = extract_text_from_content(content)
                    if text.strip():
                        role = msg.get('author', {}).get('role', 'unknown')
                        writer.add_document(tantivy.Document(
                            node_id=node_id,
                            conv_id=conv_id,
                            title=title,
                            role=role,
                            text=text
                        ))
                        msg_count += 1

            if progress_callback and i % 50 == 0:
                progress_callback(i, len(data))

        writer.commit()
        self.index.reload()

        if progress_callback:
            progress_callback(len(data), len(data))

        return msg_count

    def search(self, query_str: str, limit: int = 100) -> list[dict]:
        """Search the index, returns list of {conv_id, title, node_id, role, text, score}."""
        if not query_str.strip():
            return []

        searcher = self.index.searcher()
        try:
            query = self.index.parse_query(query_str, ["text", "title"])
        except Exception:
            # If query parsing fails, try as simple term
            query = self.index.parse_query(f'"{query_str}"', ["text", "title"])

        results = searcher.search(query, limit)
        hits = []

        for score, doc_addr in results.hits:
            doc = searcher.doc(doc_addr)
            hits.append({
                'conv_id': doc['conv_id'][0],
                'title': doc['title'][0],
                'node_id': doc['node_id'][0],
                'role': doc['role'][0],
                'text': doc['text'][0],
                'score': score
            })

        return hits

    def search_in_conversation(self, conv_id: str, query_str: str) -> list[dict]:
        """Search within a specific conversation."""
        if not query_str.strip():
            return []

        searcher = self.index.searcher()
        try:
            query = self.index.parse_query(f'conv_id:"{conv_id}" AND ({query_str})', ["text", "title"])
        except Exception:
            query = self.index.parse_query(f'conv_id:"{conv_id}" AND "{query_str}"', ["text", "title"])

        results = searcher.search(query, 1000)
        hits = []

        for score, doc_addr in results.hits:
            doc = searcher.doc(doc_addr)
            hits.append({
                'node_id': doc['node_id'][0],
                'role': doc['role'][0],
                'text': doc['text'][0],
                'score': score
            })

        return hits

    def cleanup(self):
        """Remove temporary index directory."""
        if self.index_dir and Path(self.index_dir).exists():
            shutil.rmtree(self.index_dir, ignore_errors=True)


class ConversationAnalyzerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ChatGPT Conversation Analyzer")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        self.index: ConversationIndex | None = None
        self.current_conv_id: str | None = None
        self.current_branch_path: list[str] = []

        # Filter settings (BooleanVars created in _create_widgets)
        self.filters = {}

        self._create_widgets()
        self._bind_events()

    def _create_widgets(self):
        # Menu
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open conversations.json...", command=self._open_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Export conversation...", command=self._export_conversation)
        file_menu.add_command(label="Export search results...", command=self._export_search_results)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

        # Main paned window
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel - conversation list
        left_frame = ttk.Frame(self.paned)
        self.paned.add(left_frame, weight=1)

        # Global search
        search_frame = ttk.LabelFrame(left_frame, text="Global Search", padding=5)
        search_frame.pack(fill=tk.X, pady=(0, 5))

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.bind("<Return>", lambda e: self._do_search())

        ttk.Button(search_frame, text="Search", command=self._do_search).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(search_frame, text="Clear", command=self._clear_search).pack(side=tk.LEFT, padx=(5, 0))

        # Conversation list
        list_frame = ttk.LabelFrame(left_frame, text="Conversations", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("title", "created", "modified", "branches")
        self.conv_tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")

        self.conv_tree.heading("title", text="Title", command=lambda: self._sort_conversations("title"))
        self.conv_tree.heading("created", text="Created", command=lambda: self._sort_conversations("created"))
        self.conv_tree.heading("modified", text="Modified", command=lambda: self._sort_conversations("modified"))
        self.conv_tree.heading("branches", text="Branches", command=lambda: self._sort_conversations("branches"))

        self.conv_tree.column("title", width=200, minwidth=100)
        self.conv_tree.column("created", width=120, minwidth=80)
        self.conv_tree.column("modified", width=120, minwidth=80)
        self.conv_tree.column("branches", width=60, minwidth=40, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.conv_tree.yview)
        self.conv_tree.configure(yscrollcommand=vsb.set)

        self.conv_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.conv_tree.bind("<<TreeviewSelect>>", self._on_conversation_select)

        # Right panel - conversation view
        right_frame = ttk.Frame(self.paned)
        self.paned.add(right_frame, weight=2)

        # Branch selector and local search
        top_bar = ttk.Frame(right_frame)
        top_bar.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(top_bar, text="Branch:").pack(side=tk.LEFT)
        self.branch_var = tk.StringVar()
        self.branch_combo = ttk.Combobox(top_bar, textvariable=self.branch_var, state="readonly", width=50)
        self.branch_combo.pack(side=tk.LEFT, padx=(5, 10))
        self.branch_combo.bind("<<ComboboxSelected>>", self._on_branch_select)

        ttk.Label(top_bar, text="Find:").pack(side=tk.LEFT)
        self.local_search_var = tk.StringVar()
        local_search_entry = ttk.Entry(top_bar, textvariable=self.local_search_var, width=20)
        local_search_entry.pack(side=tk.LEFT, padx=5)
        local_search_entry.bind("<Return>", lambda e: self._do_local_search())

        ttk.Button(top_bar, text="Next", command=self._find_next).pack(side=tk.LEFT)
        ttk.Button(top_bar, text="Previous", command=self._find_prev).pack(side=tk.LEFT, padx=(5, 0))

        # Filter panel
        filter_frame = ttk.LabelFrame(right_frame, text="Filters", padding=5)
        filter_frame.pack(fill=tk.X, pady=(0, 5))

        # Row 1: Roles
        role_frame = ttk.Frame(filter_frame)
        role_frame.pack(fill=tk.X, pady=(0, 3))

        ttk.Label(role_frame, text="Roles:", width=8).pack(side=tk.LEFT)

        self.filters['user'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(role_frame, text="User", variable=self.filters['user'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        self.filters['assistant'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(role_frame, text="Assistant", variable=self.filters['assistant'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        self.filters['system'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(role_frame, text="System", variable=self.filters['system'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        self.filters['reasoning'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(role_frame, text="Reasoning", variable=self.filters['reasoning'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        self.filters['tool'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(role_frame, text="Tool", variable=self.filters['tool'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        # Row 2: Content types
        content_frame = ttk.Frame(filter_frame)
        content_frame.pack(fill=tk.X, pady=(0, 3))

        ttk.Label(content_frame, text="Content:", width=8).pack(side=tk.LEFT)

        self.filters['code'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(content_frame, text="Code", variable=self.filters['code'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        self.filters['web_citation'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(content_frame, text="Web Citations", variable=self.filters['web_citation'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        self.filters['error'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(content_frame, text="Errors", variable=self.filters['error'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        # Row 3: Display options
        display_frame = ttk.Frame(filter_frame)
        display_frame.pack(fill=tk.X)

        ttk.Label(display_frame, text="Display:", width=8).pack(side=tk.LEFT)

        self.filters['show_node_id'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(display_frame, text="Node IDs", variable=self.filters['show_node_id'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        self.filters['show_model'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(display_frame, text="Model", variable=self.filters['show_model'],
                        command=self._on_filter_change).pack(side=tk.LEFT, padx=(0, 10))

        # Message display
        msg_frame = ttk.LabelFrame(right_frame, text="Messages", padding=5)
        msg_frame.pack(fill=tk.BOTH, expand=True)

        self.msg_text = tk.Text(msg_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10))
        msg_vsb = ttk.Scrollbar(msg_frame, orient=tk.VERTICAL, command=self.msg_text.yview)
        self.msg_text.configure(yscrollcommand=msg_vsb.set)

        self.msg_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        msg_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure text tags
        self.msg_text.tag_configure("user", foreground="#0066cc", font=("Consolas", 10, "bold"))
        self.msg_text.tag_configure("assistant", foreground="#006600", font=("Consolas", 10, "bold"))
        self.msg_text.tag_configure("system", foreground="#666666", font=("Consolas", 10, "italic"))
        self.msg_text.tag_configure("reasoning", foreground="#996600", font=("Consolas", 10, "italic"))
        self.msg_text.tag_configure("tool", foreground="#660066", font=("Consolas", 10))
        self.msg_text.tag_configure("code", foreground="#006666", font=("Consolas", 10))
        self.msg_text.tag_configure("web_citation", foreground="#0066aa", font=("Consolas", 10))
        self.msg_text.tag_configure("error", foreground="#cc0000", font=("Consolas", 10, "bold"))
        self.msg_text.tag_configure("highlight", background="#ffff00")
        self.msg_text.tag_configure("node_id", foreground="#999999", font=("Consolas", 8))

        # Status bar
        self.status_var = tk.StringVar(value="Open a conversations.json file to begin.")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)

        # Search state
        self.search_results: list[dict] = []
        self.local_search_matches: list[str] = []  # indices in text widget
        self.current_match_idx = -1
        self.sort_column = "modified"
        self.sort_reverse = True

    def _bind_events(self):
        self.root.bind("<Control-o>", lambda e: self._open_file())
        self.root.bind("<Control-f>", lambda e: self.search_var.set("") or None)

    def _open_file(self):
        filepath = filedialog.askopenfilename(
            title="Open Conversations File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filepath:
            return

        self.status_var.set(f"Loading {Path(filepath).name}...")
        self.root.update()

        # Clean up old index
        if self.index:
            self.index.cleanup()

        self.index = ConversationIndex()

        def load_thread():
            try:
                msg_count = self.index.load_conversations(
                    Path(filepath),
                    progress_callback=lambda i, n: self.root.after(0, lambda: self.status_var.set(f"Indexing... {i}/{n} conversations"))
                )
                self.root.after(0, lambda: self._on_load_complete(msg_count))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to load file:\n{e}"))
                self.root.after(0, lambda: self.status_var.set("Error loading file."))

        threading.Thread(target=load_thread, daemon=True).start()

    def _on_load_complete(self, msg_count: int):
        self.status_var.set(f"Loaded {len(self.index.conversations)} conversations, {msg_count} messages indexed.")
        self._populate_conversation_list()

    def _populate_conversation_list(self, filter_conv_ids: set | None = None):
        """Populate the conversation tree. If filter_conv_ids is provided, only show those."""
        self.conv_tree.delete(*self.conv_tree.get_children())

        if not self.index:
            return

        convs = []
        for conv_id, conv in self.index.conversations.items():
            if filter_conv_ids and conv_id not in filter_conv_ids:
                continue

            title = conv.get('title', 'Untitled')
            create_time = conv.get('create_time', 0)
            update_time = conv.get('update_time', 0)
            branches = self._count_branches(conv)

            convs.append({
                'conv_id': conv_id,
                'title': title,
                'create_time': create_time,
                'update_time': update_time,
                'branches': branches,
                'created_str': self._format_timestamp(create_time),
                'modified_str': self._format_timestamp(update_time)
            })

        # Sort
        key_map = {
            "title": lambda x: x['title'].lower(),
            "created": lambda x: x['create_time'] or 0,
            "modified": lambda x: x['update_time'] or 0,
            "branches": lambda x: x['branches']
        }
        convs.sort(key=key_map.get(self.sort_column, key_map["modified"]), reverse=self.sort_reverse)

        for conv in convs:
            self.conv_tree.insert("", tk.END, iid=conv['conv_id'], values=(
                conv['title'],
                conv['created_str'],
                conv['modified_str'],
                conv['branches']
            ))

    def _count_branches(self, conv: dict) -> int:
        """Count the number of leaf nodes (branch endpoints) in a conversation."""
        mapping = conv.get('mapping', {})
        leaves = 0
        for node in mapping.values():
            children = node.get('children', [])
            if not children:
                leaves += 1
        return max(1, leaves)

    def _format_timestamp(self, ts: float) -> str:
        if not ts:
            return ""
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except:
            return ""

    def _sort_conversations(self, column: str):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = column in ("modified", "created", "branches")

        if self.search_results:
            conv_ids = {r['conv_id'] for r in self.search_results}
            self._populate_conversation_list(conv_ids)
        else:
            self._populate_conversation_list()

    def _do_search(self):
        query = self.search_var.get().strip()
        if not query or not self.index:
            return

        self.status_var.set("Searching...")
        self.root.update()

        self.search_results = self.index.search(query, limit=500)

        if self.search_results:
            conv_ids = {r['conv_id'] for r in self.search_results}
            self._populate_conversation_list(conv_ids)
            self.status_var.set(f"Found {len(self.search_results)} matches in {len(conv_ids)} conversations.")
        else:
            self._populate_conversation_list(set())  # Empty
            self.status_var.set("No results found.")

    def _clear_search(self):
        self.search_var.set("")
        self.search_results = []
        self._populate_conversation_list()
        self.status_var.set(f"Showing all {len(self.index.conversations)} conversations." if self.index else "")

    def _on_conversation_select(self, event):
        selection = self.conv_tree.selection()
        if not selection:
            return

        conv_id = selection[0]
        self.current_conv_id = conv_id
        self._load_conversation(conv_id)

    def _load_conversation(self, conv_id: str):
        if not self.index or conv_id not in self.index.conversations:
            return

        conv = self.index.conversations[conv_id]
        mapping = conv.get('mapping', {})

        # Find all branches (paths from root to leaves)
        branches = self._find_all_branches(mapping)

        # Update branch combo
        branch_labels = []
        self.branch_paths = branches

        for i, path in enumerate(branches):
            # Get first user message and last assistant message as preview
            preview = self._get_branch_preview(mapping, path)
            branch_labels.append(f"Branch {i+1}: {preview}")

        self.branch_combo['values'] = branch_labels
        if branch_labels:
            self.branch_combo.current(0)
            self.current_branch_path = branches[0] if branches else []
            self._display_branch()

    def _find_all_branches(self, mapping: dict) -> list[list[str]]:
        """Find all paths from root to leaf nodes (iterative to handle deep trees)."""
        # Find root (node with no parent)
        root_id = None
        for node_id, node in mapping.items():
            if node.get('parent') is None:
                root_id = node_id
                break

        if not root_id:
            return []

        branches = []
        # Stack holds (node_id, path_so_far)
        stack = [(root_id, [])]

        while stack:
            node_id, path = stack.pop()
            current_path = path + [node_id]
            node = mapping.get(node_id, {})
            children = node.get('children', [])

            if not children:
                branches.append(current_path)
            else:
                # Add children in reverse order so first child is processed first
                for child_id in reversed(children):
                    stack.append((child_id, current_path))

        return branches

    def _get_branch_preview(self, mapping: dict, path: list[str]) -> str:
        """Get a short preview of a branch."""
        for node_id in path:
            node = mapping.get(node_id, {})
            msg = node.get('message')
            if msg:
                role = msg.get('author', {}).get('role', '')
                if role == 'assistant':
                    content = msg.get('content', {})
                    text = extract_text_from_content(content)
                    if text:
                        return text[:60] + "..." if len(text) > 60 else text
        return "(empty)"

    def _on_branch_select(self, event):
        idx = self.branch_combo.current()
        if idx >= 0 and hasattr(self, 'branch_paths') and idx < len(self.branch_paths):
            self.current_branch_path = self.branch_paths[idx]
            self._display_branch()

    def _on_filter_change(self):
        """Called when any filter checkbox changes."""
        self._display_branch()

    def _should_show_message(self, msg: dict) -> bool:
        """Check if a message should be shown based on current filter settings."""
        category = get_message_category(msg)

        # Check role-based filters
        if category == 'user' and not self.filters['user'].get():
            return False
        if category == 'assistant' and not self.filters['assistant'].get():
            return False
        if category == 'system' and not self.filters['system'].get():
            return False
        if category == 'reasoning' and not self.filters['reasoning'].get():
            return False
        if category == 'tool' and not self.filters['tool'].get():
            return False

        # Check content-type filters
        if category == 'code' and not self.filters['code'].get():
            return False
        if category == 'web_citation' and not self.filters['web_citation'].get():
            return False
        if category == 'error' and not self.filters['error'].get():
            return False

        return True

    def _display_branch(self):
        """Display the current branch's messages."""
        self.msg_text.configure(state=tk.NORMAL)
        self.msg_text.delete("1.0", tk.END)

        if not self.index or not self.current_conv_id:
            self.msg_text.configure(state=tk.DISABLED)
            return

        conv = self.index.conversations[self.current_conv_id]
        mapping = conv.get('mapping', {})

        show_node_id = self.filters['show_node_id'].get()
        show_model = self.filters['show_model'].get()

        for node_id in self.current_branch_path:
            node = mapping.get(node_id, {})
            msg = node.get('message')

            if not msg:
                continue

            # Check filters
            if not self._should_show_message(msg):
                continue

            content = msg.get('content', {})
            text = extract_text_from_content(content)
            if not text.strip():
                continue

            # Determine category for styling
            category = get_message_category(msg)
            role = msg.get('author', {}).get('role', 'unknown')

            # Build header
            # Use role for display, but category determines if it's special
            if category == 'reasoning':
                display_role = "Reasoning"
            elif category == 'tool':
                display_role = "Tool"
            elif category == 'code':
                display_role = "Code"
            elif category == 'web_citation':
                display_role = "Citation"
            elif category == 'error':
                display_role = "Error"
            else:
                display_role = role.capitalize()

            # Get timestamp
            create_time = msg.get('create_time')
            time_str = f" ({self._format_timestamp(create_time)})" if create_time else ""

            # Build optional parts
            model_str = ""
            if show_model:
                model_slug = msg.get('metadata', {}).get('model_slug', '')
                if model_slug:
                    model_str = f" [{model_slug}]"

            node_str = ""
            if show_node_id:
                node_str = f" Node: {node_id}"

            # Insert header
            header = f"--- {display_role}{time_str}{model_str}{node_str} ---\n"
            tag = category if category in ('user', 'assistant', 'system', 'reasoning', 'tool', 'code', 'web_citation', 'error') else 'system'
            self.msg_text.insert(tk.END, header, tag)

            # Insert message text
            self.msg_text.insert(tk.END, text + "\n\n")

        self.msg_text.configure(state=tk.DISABLED)
        self.local_search_matches = []
        self.current_match_idx = -1

    def _do_local_search(self):
        """Search within the current conversation display."""
        query = self.local_search_var.get().strip()
        if not query:
            return

        # Clear previous highlights
        self.msg_text.tag_remove("highlight", "1.0", tk.END)
        self.local_search_matches = []

        # Find all occurrences
        start = "1.0"
        while True:
            pos = self.msg_text.search(query, start, stopindex=tk.END, nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(query)}c"
            self.msg_text.tag_add("highlight", pos, end)
            self.local_search_matches.append(pos)
            start = end

        if self.local_search_matches:
            self.current_match_idx = 0
            self.msg_text.see(self.local_search_matches[0])
            self.status_var.set(f"Found {len(self.local_search_matches)} matches. Use Next/Previous to navigate.")
        else:
            self.status_var.set("No matches found in current view.")

    def _find_next(self):
        if not self.local_search_matches:
            self._do_local_search()
            return

        self.current_match_idx = (self.current_match_idx + 1) % len(self.local_search_matches)
        self.msg_text.see(self.local_search_matches[self.current_match_idx])

    def _find_prev(self):
        if not self.local_search_matches:
            return

        self.current_match_idx = (self.current_match_idx - 1) % len(self.local_search_matches)
        self.msg_text.see(self.local_search_matches[self.current_match_idx])

    def _export_conversation(self):
        if not self.current_conv_id or not self.index:
            messagebox.showwarning("No Conversation", "Select a conversation first.")
            return

        filepath = filedialog.asksaveasfilename(
            title="Export Conversation",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("Markdown", "*.md"), ("JSON", "*.json"), ("All files", "*.*")]
        )
        if not filepath:
            return

        conv = self.index.conversations[self.current_conv_id]

        if filepath.endswith('.json'):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(conv, f, indent=2, ensure_ascii=False)
        else:
            # Export current branch as text
            mapping = conv.get('mapping', {})
            lines = [f"# {conv.get('title', 'Untitled')}\n\n"]

            for node_id in self.current_branch_path:
                node = mapping.get(node_id, {})
                msg = node.get('message')
                if not msg:
                    continue

                role = msg.get('author', {}).get('role', 'unknown')
                content = msg.get('content', {})
                if content.get('content_type') != 'text':
                    continue

                parts = content.get('parts', [])
                text = ' '.join(str(p) for p in parts if p)
                if text.strip():
                    lines.append(f"## {role.capitalize()}\n\n{text}\n\n")

            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)

        self.status_var.set(f"Exported to {Path(filepath).name}")

    def _export_search_results(self):
        if not self.search_results:
            messagebox.showwarning("No Results", "Perform a search first.")
            return

        filepath = filedialog.asksaveasfilename(
            title="Export Search Results",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("JSON", "*.json"), ("All files", "*.*")]
        )
        if not filepath:
            return

        if filepath.endswith('.json'):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.search_results, f, indent=2, ensure_ascii=False)
        else:
            lines = [f"Search Results: {self.search_var.get()}\n", "=" * 50 + "\n\n"]
            for r in self.search_results:
                lines.append(f"[{r['title']}] ({r['role']})\n")
                lines.append(f"{r['text'][:500]}{'...' if len(r['text']) > 500 else ''}\n")
                lines.append("-" * 30 + "\n\n")

            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)

        self.status_var.set(f"Exported {len(self.search_results)} results to {Path(filepath).name}")


def main():
    root = tk.Tk()
    app = ConversationAnalyzerApp(root)

    def on_close():
        if app.index:
            app.index.cleanup()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == '__main__':
    main()
