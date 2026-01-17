# FileBuddy

Voice-controlled AI file manager powered by OpenAI Realtime API. Organize, search, create, and manage files safely through natural conversation.

## Features

- **Voice Control** - Natural language file operations via LiveKit
- **Smart Search** - Find files by name, content, type, or pattern
- **Auto-Organization** - Organize files by type, date, size, or extension
- **File Creation** - Create files, folders, and entire project structures
- **Batch Operations** - Move, copy, rename multiple files at once
- **Undo/Redo** - Rollback any operation within 24 hours
- **Safety First** - Protected paths, confirmation prompts, audit logging
- **Complete Audit Trail** - Every action logged for compliance

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- OpenAI API key
- LiveKit account

### Installation

```bash
# Clone repository
git clone https://github.com/tanishra/file-buddy.git
cd file-buddy

# Install dependencies with uv
uv sync

# Create environment file
cp .env.example .env.local
```

### Configuration

Edit `.env.local`:

```bash
OPENAI_API_KEY=your_openai_api_key
LIVEKIT_URL=your_livekit_url
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
```

### Run

```bash
uv run main.py console
```

## Usage Examples

**Organize Files:**
```
You: "Show me what's in my Downloads"
FileBuddy: "I found 47 files: 12 PDFs, 20 images..."

You: "Organize them by file type"
FileBuddy: "Ready to organize 47 files into 4 folders?"

You: "Yes"
FileBuddy: "Organized 47 files! Say 'undo' to revert."
```

**Create Files:**
```
You: "Create a Python file called calculator.py"
FileBuddy: "Created calculator.py"
```

**Search & Delete:**
```
You: "Find all .tmp files"
FileBuddy: "Found 23 .tmp files"

You: "Delete them"
FileBuddy: "Delete 23 files? Say 'confirm delete'"

You: "confirm delete"
FileBuddy: "Deleted 23 files (moved to trash)"
```

## Safety Features

- **Protected Paths** - System folders are off-limits
- **User Confirmation** - Required for destructive operations
- **Rollback System** - 24-hour undo window for all operations
- **Audit Logging** - Complete operation history
- **Trash Safety** - Files deleted to trash, not permanent

## Project Structure

```
FileBuddy/
├── main.py                 # Entry point
├── tools/                  # File operation tools
├── core/                   # Core systems (confirmation, snapshot, audit)
├── config/                 # Configuration & prompts
├── utils/                  # Utilities & helpers
├── data/
│   ├── snapshots/         # Rollback data
│   └── audit_logs/        # Operation logs
```

## Logging

All operations are logged:

- **Console Logs**: Real-time structured JSON
- **Audit Logs**: `data/audit_logs/audit_YYYY-MM-DD.jsonl`

## Security

- Never operates on system directories (`/System`, `/Windows`, `/usr`, etc.)
- Requires explicit confirmation for deletions
- All operations are auditable
- No data sent externally except to OpenAI API

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## Acknowledgments

- [LiveKit](https://livekit.io/) - Real-time voice infrastructure
- [OpenAI](https://platform.openai.com/) - Realtime API
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager