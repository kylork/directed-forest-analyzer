# ChatGPT Conversation Analyzer - HTML Version

## Overview

This is an HTML/JavaScript version of the ChatGPT Conversation Analyzer, converted from the original Python/tkinter GUI. It runs entirely in your web browser with no server or installation required.

## Features

### Core Functionality
- **Import conversations.json** - Load your ChatGPT export file directly in the browser
- **Branch navigation** - Navigate through conversation branches created by edits and regenerations
- **Global search** - Search across all conversations for specific text
- **Local search** - Find text within the currently displayed conversation
- **Sorting** - Sort conversations by title, created date, modified date, or branch count
- **Filtering** - Filter messages by type (User, Assistant, System, Reasoning, Tool, Code, Citations, Errors)
- **Export** - Export conversations or search results as text files

### Message Type Support
The analyzer handles all known ChatGPT content types:
- **text** - Standard text messages
- **multimodal_text** - Mixed content (text + images/audio)
- **code** - Code blocks
- **execution_output** - Code interpreter output
- **thoughts** - o3/o4 reasoning (array of {summary, content})
- **reasoning_recap** - "Thought for Xs" summary
- **tether_quote** - Web citations with domain/title/url
- **system_error** - Error messages

### Filtering Options
- **Roles**: User, Assistant, System, Reasoning, Tool
- **Content Types**: Code, Web Citations, Errors
- **Display Options**: Node IDs, Model names

## How to Use

### Step 1: Get Your ChatGPT Export
1. Go to ChatGPT settings
2. Navigate to Data Controls → Export Data
3. Wait for the email with your export
4. Download and extract the `conversations.json` file

### Step 2: Open the Analyzer
Simply open `conversation_analyzer.html` in any modern web browser:
- Chrome/Edge/Brave (recommended)
- Firefox
- Safari

No installation or server required!

### Step 3: Load Your Conversations
1. Click "File: Open conversations.json (Ctrl+O)" in the menu bar, or press Ctrl+O
2. Select your `conversations.json` file
3. Wait for the conversations to load and index

### Step 4: Browse and Search
- **Select a conversation** - Click any row in the conversation list
- **Switch branches** - Use the Branch dropdown to view different conversation paths
- **Global search** - Enter text in the "Global Search" box and click Search
- **Local search** - Use the "Find" box to search within the current conversation
- **Apply filters** - Check/uncheck filter options to show/hide message types
- **Sort** - Click column headers to sort by title, date, or branch count

### Keyboard Shortcuts
- **Ctrl+O** - Open file dialog
- **Ctrl+F** - Focus global search box
- **Enter** - Execute search (in search boxes)

## Differences from Python Version

### What's the Same
- All core functionality is preserved
- Identical UI layout and design
- Same message categorization and filtering
- Same branch navigation logic
- Same export capabilities

### What's Different
- **Search**: Uses simple JavaScript text search instead of Tantivy (still fast for typical export sizes)
- **File loading**: Uses browser File API instead of file dialogs
- **Performance**: May be slightly slower on very large exports (1000+ conversations)
- **No installation**: Runs directly in browser, no Python dependencies needed

## Technical Details

### Browser Compatibility
- Requires modern browser with ES6 support
- Uses native JavaScript (no external libraries)
- File size limit: depends on browser memory (typically handles 200+ MB files)

### Data Privacy
- **All processing happens locally in your browser**
- No data is uploaded or sent anywhere
- No internet connection required after loading the page
- Your conversations never leave your computer

### File Structure
The analyzer is a single self-contained HTML file containing:
- HTML structure
- CSS styling
- JavaScript logic

You can easily:
- Copy it to any device
- Email it to yourself
- Store it on a USB drive
- Use it offline

## Troubleshooting

### Large File Loading
If your export is very large (500+ MB):
1. The browser may take 30-60 seconds to load
2. Consider using Chrome/Edge which handle large files better
3. Close other browser tabs to free memory

### Search Not Working
- Make sure you've loaded a conversations.json file first
- Try clearing the search and searching again
- Check that your search term appears in the conversations

### Filtering Issues
- Filters apply only to message display, not the conversation list
- Try toggling filters on/off to refresh the view
- Some messages may be empty and won't show even with filters enabled

## Comparison with Python Version

| Feature | Python Version | HTML Version |
|---------|---------------|--------------|
| Installation | Requires Python + dependencies | None - open in browser |
| Search Engine | Tantivy (Rust) | JavaScript text search |
| Performance | Faster for 1000+ convs | Fast for typical sizes |
| Portability | Requires Python install | Works anywhere |
| File Size | Multiple .py files | Single HTML file |
| Dependencies | tkinter, tantivy | None |

## Credits

Converted from the original Python/tkinter version by analyzing the source code structure and replicating all functionality in vanilla HTML/CSS/JavaScript.

Original features include:
- Tantivy-powered search with stop word preservation
- Iterative DFS for branch finding (avoids Python recursion limits)
- Support for all ChatGPT content types including o3/o4 reasoning
- Color-coded message categories

## License

Same as the original project.
