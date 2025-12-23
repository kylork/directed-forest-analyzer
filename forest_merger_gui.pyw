#!/usr/bin/env python3
"""
Directed Forest Merger - GUI Application

A user-friendly GUI for comparing and merging ChatGPT conversation exports.
"""

import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Any
from datetime import datetime


class ForestMergerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ChatGPT Conversation Merger")
        self.root.geometry("900x600")
        self.root.minsize(700, 500)

        # Data storage
        self.older_file: Path | None = None
        self.newer_file: Path | None = None
        self.older_data: dict[str, dict] | None = None
        self.newer_data: dict[str, dict] | None = None
        self.missing_conversations: list[dict] = []
        self.sort_column: str = "nodes"
        self.sort_reverse: bool = True

        self._create_widgets()

    def _create_widgets(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # File selection frame
        file_frame = ttk.LabelFrame(main_frame, text="Select Conversation Files", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        # Older file
        ttk.Label(file_frame, text="Older (Past) File:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.older_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.older_path_var, width=60, state='readonly').grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="Browse...", command=self._browse_older).grid(row=0, column=2, pady=2)
        self.older_count_var = tk.StringVar(value="")
        ttk.Label(file_frame, textvariable=self.older_count_var, foreground="gray").grid(row=0, column=3, padx=10)

        # Newer file
        ttk.Label(file_frame, text="Newer (Present) File:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.newer_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.newer_path_var, width=60, state='readonly').grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="Browse...", command=self._browse_newer).grid(row=1, column=2, pady=2)
        self.newer_count_var = tk.StringVar(value="")
        ttk.Label(file_frame, textvariable=self.newer_count_var, foreground="gray").grid(row=1, column=3, padx=10)

        # Compare button
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(btn_frame, text="Compare Files", command=self._compare_files).pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="")
        ttk.Label(btn_frame, textvariable=self.status_var, foreground="blue").pack(side=tk.LEFT, padx=20)

        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text="Missing Conversations (in Older but not in Newer)", padding="10")
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Treeview for results
        columns = ("title", "created", "modified", "nodes", "conversation_id")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings", selectmode="extended")

        self.tree.heading("title", text="Title", anchor=tk.W, command=lambda: self._sort_by_column("title"))
        self.tree.heading("created", text="Created", anchor=tk.W, command=lambda: self._sort_by_column("created"))
        self.tree.heading("modified", text="Modified", anchor=tk.W, command=lambda: self._sort_by_column("modified"))
        self.tree.heading("nodes", text="Nodes", anchor=tk.CENTER, command=lambda: self._sort_by_column("nodes"))
        self.tree.heading("conversation_id", text="Conversation ID", anchor=tk.W, command=lambda: self._sort_by_column("conversation_id"))

        self.tree.column("title", width=250, minwidth=150)
        self.tree.column("created", width=140, minwidth=100)
        self.tree.column("modified", width=140, minwidth=100)
        self.tree.column("nodes", width=60, minwidth=50, anchor=tk.CENTER)
        self.tree.column("conversation_id", width=280, minwidth=200)

        # Scrollbars
        vsb = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(results_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)

        # Summary and merge frame
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X)

        self.summary_var = tk.StringVar(value="Load two files and click Compare to see missing conversations.")
        ttk.Label(bottom_frame, textvariable=self.summary_var).pack(side=tk.LEFT)

        ttk.Button(bottom_frame, text="Merge Files...", command=self._merge_files).pack(side=tk.RIGHT)
        ttk.Button(bottom_frame, text="Copy Selected IDs", command=self._copy_selected_ids).pack(side=tk.RIGHT, padx=5)

    def _browse_older(self):
        filepath = filedialog.askopenfilename(
            title="Select Older (Past) Conversations File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            self.older_file = Path(filepath)
            self.older_path_var.set(filepath)
            self._load_file("older")

    def _browse_newer(self):
        filepath = filedialog.askopenfilename(
            title="Select Newer (Present) Conversations File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            self.newer_file = Path(filepath)
            self.newer_path_var.set(filepath)
            self._load_file("newer")

    def _load_file(self, which: str):
        filepath = self.older_file if which == "older" else self.newer_file
        count_var = self.older_count_var if which == "older" else self.newer_count_var

        try:
            self.status_var.set(f"Loading {filepath.name}...")
            self.root.update()

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            conversations = {conv['conversation_id']: conv for conv in data}

            if which == "older":
                self.older_data = conversations
            else:
                self.newer_data = conversations

            count_var.set(f"({len(conversations)} conversations)")
            self.status_var.set("")

        except Exception as e:
            count_var.set("(error)")
            self.status_var.set("")
            messagebox.showerror("Error", f"Failed to load file:\n{e}")

    def _compare_files(self):
        if self.older_data is None or self.newer_data is None:
            messagebox.showwarning("Missing Files", "Please load both an older and newer file first.")
            return

        self.status_var.set("Comparing...")
        self.root.update()

        # Clear existing results
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Find missing conversations
        older_ids = set(self.older_data.keys())
        newer_ids = set(self.newer_data.keys())
        missing_ids = older_ids - newer_ids

        self.missing_conversations = []
        for cid in missing_ids:
            conv = self.older_data[cid]
            create_time = conv.get('create_time', 0)
            update_time = conv.get('update_time', 0)
            self.missing_conversations.append({
                'conversation_id': cid,
                'title': conv.get('title', 'Untitled'),
                'nodes': len(conv.get('mapping', {})),
                'create_time': create_time,
                'update_time': update_time,
                'created_str': self._format_timestamp(create_time),
                'modified_str': self._format_timestamp(update_time)
            })

        # Sort by current sort column
        self._sort_conversations()

        # Populate treeview
        self._populate_tree()

        # Update summary
        common = len(older_ids & newer_ids)
        new_in_newer = len(newer_ids - older_ids)
        self.summary_var.set(
            f"Missing: {len(self.missing_conversations)} | "
            f"Common: {common} | "
            f"New in Newer: {new_in_newer} | "
            f"Total after merge: {len(older_ids | newer_ids)}"
        )
        self.status_var.set("")

    def _format_timestamp(self, ts: float) -> str:
        """Convert Unix timestamp to readable date string."""
        if not ts:
            return ""
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except:
            return ""

    def _sort_by_column(self, column: str):
        """Sort treeview by clicked column."""
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            # Default sort direction per column type
            self.sort_reverse = column in ("nodes", "created", "modified")

        self._sort_conversations()
        self._populate_tree()

    def _sort_conversations(self):
        """Sort the missing_conversations list by current sort column."""
        key_map = {
            "title": lambda x: x['title'].lower(),
            "created": lambda x: x['create_time'] or 0,
            "modified": lambda x: x['update_time'] or 0,
            "nodes": lambda x: x['nodes'],
            "conversation_id": lambda x: x['conversation_id']
        }
        key_func = key_map.get(self.sort_column, key_map["nodes"])
        self.missing_conversations.sort(key=key_func, reverse=self.sort_reverse)

    def _populate_tree(self):
        """Clear and repopulate the treeview with sorted data."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        for conv in self.missing_conversations:
            self.tree.insert("", tk.END, values=(
                conv['title'],
                conv['created_str'],
                conv['modified_str'],
                conv['nodes'],
                conv['conversation_id']
            ))

    def _copy_selected_ids(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Select one or more rows to copy their IDs.")
            return

        ids = [self.tree.item(item)['values'][4] for item in selected]
        self.root.clipboard_clear()
        self.root.clipboard_append('\n'.join(ids))
        self.status_var.set(f"Copied {len(ids)} ID(s) to clipboard")

    def _merge_files(self):
        if self.older_data is None or self.newer_data is None:
            messagebox.showwarning("Missing Files", "Please load both files first.")
            return

        output_path = filedialog.asksaveasfilename(
            title="Save Merged Conversations",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="merged_conversations.json"
        )

        if not output_path:
            return

        try:
            self.status_var.set("Merging...")
            self.root.update()

            # Merge: include all conversations, prefer larger version if duplicate
            merged = {}
            all_ids = set(self.older_data.keys()) | set(self.newer_data.keys())

            for cid in all_ids:
                older_conv = self.older_data.get(cid)
                newer_conv = self.newer_data.get(cid)

                if older_conv is None:
                    merged[cid] = newer_conv
                elif newer_conv is None:
                    merged[cid] = older_conv
                else:
                    # Both exist - use larger one
                    older_size = len(older_conv.get('mapping', {}))
                    newer_size = len(newer_conv.get('mapping', {}))
                    merged[cid] = older_conv if older_size >= newer_size else newer_conv

            # Sort by update_time
            result = list(merged.values())
            result.sort(key=lambda x: x.get('update_time', 0), reverse=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False)

            self.status_var.set("")
            messagebox.showinfo("Success", f"Merged {len(result)} conversations to:\n{output_path}")

        except Exception as e:
            self.status_var.set("")
            messagebox.showerror("Error", f"Failed to merge:\n{e}")


def main():
    root = tk.Tk()
    app = ForestMergerApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
