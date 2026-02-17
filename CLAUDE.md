# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DISCOVER-Utils is a Python utility package designed to work with the [DISCOVER framework](https://github.com/hcmlab/discover). It provides data handling, processing, and annotation utilities for multimedia data analysis, particularly focused on annotation workflows and dataset management.

The package is structured around three main components:
- **Data layer** (`discover_utils/data/`): Core data types, handlers for various backends (files, databases), and data providers
- **Processing scripts** (`discover_utils/scripts/`): Command-line tools for training and processing workflows
- **Interfaces** (`discover_utils/interfaces/`): Abstract base classes for server modules and processors

## Commands

### Installation and Development
```bash
# Install package in development mode
pip install -e .

# Install with optional dependencies
pip install -e .[decord,pymovie,pyav]
```

### Documentation
```bash
# Build Sphinx documentation (from docs/ directory)
cd docs
sphinx-build docsource docbuild

# The documentation is automatically built and deployed via GitHub Actions
```

### Command-line Tools
The package provides two main CLI commands:

```bash
# Data processing with NOVA-server modules
du-process --dataset "test" --db_host "127.0.0.1" --db_port "37317" \
  --db_user "user" --db_password "pass" \
  --trainer_file_path "path/to/trainer.trainer" \
  --sessions '["session1", "session2"]' \
  --data '[{"src": "db:anno", "scheme": "transcript", "annotator": "test", "role": "testrole"}]'

# Training (currently not implemented)
du-train
```

### Releasing
To release a new version:

1. Update the version in `discover_utils/__init__.py` (`_PATCH_VERSION`, `_MINOR_VERSION`, or `_MAJOR_VERSION`)
2. Commit the changes
3. Push to remote and create a tag to trigger the release action:
```bash
git push
git tag v<VERSION>
git push origin v<VERSION>
```

## Architecture

### Data Management
- **MetaData class** (`discover_utils/data/data.py:11`): Base metadata container for all data objects
- **DatasetManager** (`discover_utils/data/provider/data_manager.py`): Manages entire datasets with multiple sessions
- **SessionManager**: Handles individual session data within datasets
- **DatasetIterator** (`discover_utils/data/provider/dataset_iterator.py`): Provides iterable access to dataset chunks

### Data Types
- **Stream**: Continuous data streams (audio, video, sensor data)
- **Annotation**: Discrete and continuous annotation data
- **Data handlers**: Support for file-based storage, MongoDB, and URL-based data sources

### Video Backend Support
The package supports multiple video reading backends:
- **decord**: Fast video decoder (optional dependency)
- **imageio**: General-purpose image/video I/O
- **moviepy**: Video editing and processing
- **pyav**: Python bindings for FFmpeg

### Processing Architecture
- **Processor base class** (`discover_utils/interfaces/server_module.py:13`): Abstract interface for all data processors
- **Predictor**: Processes data and generates predictions
- **Extractor**: Extracts features from input data
- **SSI Integration**: Uses SSI (Social Signal Interpretation) trainer files and XML configurations

### Key Processing Flow
1. Load trainer configuration from SSI XML files
2. Initialize appropriate data provider (DatasetManager or DatasetIterator)
3. Load processor module dynamically from trainer script path
4. Process data through the loaded module
5. Save results back to database or file system

## Configuration

### Environment Variables
- `CACHE_DIR`: Directory for caching processed data
- `TMP_DIR`: Temporary directory for processing

### Database Connection
MongoDB connections are configured via command-line arguments:
- `--db_host`, `--db_port`: Database connection details
- `--db_user`, `--db_password`: Authentication credentials
- TLS connections are supported for secure database access

### Video Backend Selection
Choose video backend via `--video_backend` parameter:
- `DECORD` (default, requires eva-decord)
- `IMAGEIO`
- `MOVIEPY` 
- `PYAV`
- investigate why num_samples (in absolute count) / sample_rate (in Hz) = duration (in milliseconds) (wrong!) for an audio stream