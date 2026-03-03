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
