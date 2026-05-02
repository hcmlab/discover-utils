# DISCOVER-Utils

[![PyPI version](https://img.shields.io/pypi/v/hcai-discover-utils)](https://pypi.org/project/hcai-discover-utils/)
[![Python](https://img.shields.io/pypi/pyversions/hcai-discover-utils)](https://pypi.org/project/hcai-discover-utils/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://hcmlab.github.io/discover-utils/docbuild/)

DISCOVER-Utils is a Python utility package for data handling, processing, and annotation of multimedia data. It is designed to work with the [DISCOVER](https://github.com/hcmlab/discover) framework or as a stand-alone library.

## Features

- **Data handling** — Unified access to streams (audio, video, sensor data) and annotations (discrete, continuous) via file, MongoDB, or URL backends
- **Multiple video backends** — Choose between decord, imageio, moviepy, or pyav for video decoding
- **Dataset management** — Iterate over multi-session datasets with `DatasetManager` and `DatasetIterator`
- **Processing pipeline** — Run DISCOVER server modules from the command line for feature extraction and prediction
- **SSI compatibility** — Read and write SSI trainer files and XML configurations

## Installation

```bash
pip install hcai-discover-utils
```

### Optional video backends

```bash
# Fast video decoding with decord
pip install hcai-discover-utils[decord]

# PyAV (FFmpeg bindings)
pip install hcai-discover-utils[pyav]

# MoviePy
pip install hcai-discover-utils[pymovie]
```

## Getting Started

### Command-line tools

**Process data** with DISCOVER server modules:

```bash
du-process \
  --dataset "my_dataset" \
  --db_host "127.0.0.1" --db_port "27017" \
  --db_user "user" --db_password "pass" \
  --trainer_file_path "path/to/trainer.trainer" \
  --sessions '["session1", "session2"]' \
  --data '[{"src": "db:anno", "scheme": "transcript", "annotator": "test", "role": "testrole"}]'
```

#### File mode (no database)

Read inputs and write outputs directly from/to disk, without a NOVA database. Use `file:` sources and supply a path via `uri` (static, single session) or `uri_template` (per-session paths via `{dataset}` and `{session}` placeholders):

```bash
du-process \
  --dataset "my_study" \
  --trainer_file_path "path/to/trainer.trainer" \
  --sessions '["session_a", "session_b"]' \
  --data '[
    {
      "id": "video",
      "type": "input",
      "src": "file:stream:video",
      "uri_template": "/data/{dataset}/{session}/video.mp4"
    },
    {
      "id": "valence",
      "type": "output",
      "src": "file:annotation:continuous",
      "uri_template": "/outputs/{dataset}/{session}/valence.annotation",
      "sample_rate": 30,
      "min_val": -1,
      "max_val": 1
    }
  ]'
```

Each session resolves its own input and output paths. Output annotation descriptors may carry scheme metadata that is used when no annotation file exists yet:

- `file:annotation:continuous`: `sample_rate`, `min_val`, `max_val` (defaults: `1`, `0`, `1`).
- `file:annotation:discrete`: `classes` as an `{id: label}` map.

This matters for modules that resample continuous outputs to the scheme's `sample_rate` — without explicit metadata, outputs default to 1 Hz.

Notes:

- `uri` and `uri_template` are filesystem paths (absolute or relative to the working directory). There is no implicit base directory.
- `uri_template` placeholders that reference `{dataset}` or `{session}` must have non-empty values; otherwise `resolve_file_uri` raises `ValueError`.
- `uri_template` takes precedence over `uri` when both are present.

### Python API

```python
from discover_utils.data.provider.data_manager import DatasetManager

# Set up a dataset manager for your sessions
dm = DatasetManager(
    dataset="my_dataset",
    db_host="127.0.0.1",
    db_port=27017,
    db_user="user",
    db_password="pass",
    sessions=["session1"],
    data_description=[...],
)
```

## Documentation

Full API documentation is available at [hcmlab.github.io/discover-utils/docbuild/](https://hcmlab.github.io/discover-utils/docbuild/).

## Citation

If you use DISCOVER or DISCOVER-Utils in your research, please cite:

```bibtex
@article{hallmen2025discover,
  title     = {DISCOVER: a Data-driven Interactive System for Comprehensive
               Observation, Visualization, and ExploRation of human behavior},
  author    = {Hallmen, Tobias and Schiller, Dominik and others},
  journal   = {Frontiers in Digital Health},
  volume    = {7},
  pages     = {1638539},
  year      = {2025},
  publisher = {Frontiers}
}
```

## License

This project is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0).
