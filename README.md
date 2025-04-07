# OllamaUtil

A command-line utility to manage the Ollama cache, making it easier to maintain and move Ollama models between different storage locations. Useful for managing models across internal and external storage.

## Features

- List installed Ollama models with details about their storage location (internal/external cache)
- Toggle between internal and external Ollama cache directories using symbolic links
- Migrate model files between internal and external caches with:
  - SHA-256 checksum validation
  - Progress bars for large files
  - Metadata preservation
  - Blob file handling
- Remove models from either or both caches
- Pull models from Ollama.com
- Push models to Ollama.com (personal repositories only)
- Supports multiple model tags and versions

## Installation

From PyPI:
```bash
pip install ollamautil
```

From source:
```bash
git clone https://github.com/yourusername/ollamautil.git
cd ollamautil
pip install -e .
```

## Configuration

Set the following environment variables before using:

```bash
# Required: Path to internal Ollama models directory
export OLLAMAUTIL_INTERNAL_DIR="/path/to/internal/ollama/models"

# Required: Path to external Ollama models directory
export OLLAMAUTIL_EXTERNAL_DIR="/path/to/external/ollama/models"

# Optional: List of files to ignore (defaults to [".DS_Store"])
export OLLAMAUTIL_FILE_IGNORE='[".DS_Store", "other_file_to_ignore"]'
```

Add these to your `.bashrc`, `.zshrc`, or equivalent to make them permanent.

## Usage

Start the utility:
```bash
ollamautil
```

### Main Menu Options

1. **Copy** - Migrate files between internal and external cache
   - Select models to copy
   - Choose direction (internal ↔ external)
   - Option to overwrite existing files
   - Automatic checksum validation

2. **Toggle** - Switch between internal and external cache
   - Shows current cache location
   - Option to migrate files before switching
   - Updates symbolic links automatically

3. **Remove** - Delete models from cache
   - Select models to remove
   - Remove from internal, external, or both
   - Confirmation required

4. **Pull** - Download models from Ollama.com
   - Select models to pull
   - Supports library and custom models
   - Shows download progress

5. **Push** - Upload models to Ollama.com
   - Supports personal repositories only
   - Format: username/model:tag

## Dependencies

- prettytable - For displaying model tables
- tqdm - For progress bars during file operations
- ollama - For interacting with Ollama API

## Development

To contribute or modify:

1. Clone the repository
2. Install in development mode:
```bash
pip install -e .
```
3. Run tests:
```bash
python -m unittest tests/test_ollamautil.py
```

## License

GPL-3.0 - See LICENSE.md for details
