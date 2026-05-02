"""Tests for session-parameterized file-mode URI resolution and output annotation metadata.

Covers:
- resolve_file_uri() helper: uri_template with {dataset}/{session} placeholders,
  plain uri fallback, and missing key error.
- SessionManager.load(): two sessions resolving different file paths via uri_template.
- SessionManager.save(): two sessions writing to different output paths via uri_template.
- Continuous output template retaining sample_rate/min_val/max_val from desc.
- Discrete output template using classes from desc.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from discover_utils.data.annotation import (
    ContinuousAnnotation,
    ContinuousAnnotationScheme,
    DiscreteAnnotation,
    DiscreteAnnotationScheme,
)
from discover_utils.data.provider.data_manager import (
    DatasetManager,
    SessionManager,
    resolve_file_uri,
)


# ---------------------------------------------------------------------------
# Unit tests for resolve_file_uri
# ---------------------------------------------------------------------------

class TestResolveFileUri:
    def test_plain_uri_returned_as_path(self):
        desc = {"uri": "/data/session_a/video.mp4"}
        result = resolve_file_uri(desc, dataset="ds", session="sess")
        assert result == Path("/data/session_a/video.mp4")

    def test_uri_template_with_session(self):
        desc = {"uri_template": "/data/{session}/video.mp4"}
        result = resolve_file_uri(desc, dataset="myds", session="session_a")
        assert result == Path("/data/session_a/video.mp4")

    def test_uri_template_with_dataset_and_session(self):
        desc = {"uri_template": "/data/{dataset}/{session}/child.video.mp4"}
        result = resolve_file_uri(desc, dataset="myds", session="session_b")
        assert result == Path("/data/myds/session_b/child.video.mp4")

    def test_uri_template_takes_priority_over_uri(self):
        desc = {
            "uri_template": "/data/{session}/video.mp4",
            "uri": "/data/static/video.mp4",
        }
        result = resolve_file_uri(desc, dataset="ds", session="sess_x")
        assert result == Path("/data/sess_x/video.mp4")

    def test_missing_uri_raises_key_error(self):
        desc = {"src": "file:stream:video", "id": "video"}
        with pytest.raises(KeyError):
            resolve_file_uri(desc, dataset="ds", session="sess")

    def test_none_dataset_for_dataset_placeholder_raises(self):
        desc = {"uri_template": "/data/{dataset}/{session}/file.mp4"}
        with pytest.raises(ValueError):
            resolve_file_uri(desc, dataset=None, session="sess")

    def test_none_session_for_session_placeholder_raises(self):
        desc = {"uri_template": "/data/{dataset}/{session}/file.mp4"}
        with pytest.raises(ValueError):
            resolve_file_uri(desc, dataset="ds", session=None)

    def test_none_dataset_ok_when_template_does_not_reference_it(self):
        desc = {"uri_template": "/data/{session}/file.mp4"}
        result = resolve_file_uri(desc, dataset=None, session="sess")
        assert result == Path("/data/sess/file.mp4")

    def test_braces_in_legacy_uri_are_not_formatted(self):
        desc = {"uri": "/data/weird{not_a_placeholder}/file.mp4"}
        result = resolve_file_uri(desc, dataset="ds", session="sess")
        assert result == Path("/data/weird{not_a_placeholder}/file.mp4")


# ---------------------------------------------------------------------------
# SessionManager.load() — two sessions load different paths via uri_template
# ---------------------------------------------------------------------------

class TestSessionManagerLoadUriTemplate:
    """Tests that file-mode inputs resolve to session-specific paths."""

    def _make_sm(self, session: str, tmp_path: Path) -> SessionManager:
        desc = [
            {
                "id": "video",
                "type": "input",
                "src": "file:stream:video",
                "uri_template": str(tmp_path / "{session}" / "video.mp4"),
            }
        ]
        return SessionManager(
            dataset="myds",
            data_description=desc,
            session=session,
            source_context={},
        )

    def test_different_sessions_load_different_paths(self, tmp_path):
        # Create dummy files for two sessions
        for sess in ("session_a", "session_b"):
            sess_dir = tmp_path / sess
            sess_dir.mkdir()
            # Write a minimal mp4-like stub; we only need FileHandler to
            # resolve the path – mock the load so no actual video decoding
            (sess_dir / "video.mp4").write_bytes(b"")

        loaded_fps = []

        def fake_load(fp, header_only=False):
            loaded_fps.append(fp)
            raise FileNotFoundError("mocked – trigger fallback")

        with patch(
            "discover_utils.data.handler.file_handler.FileHandler.load",
            side_effect=fake_load,
        ):
            for sess in ("session_a", "session_b"):
                sm = self._make_sm(sess, tmp_path)
                # load() will hit FileNotFoundError for output headers; for
                # inputs it will propagate, so catch it here
                try:
                    sm.load()
                except FileNotFoundError:
                    pass

        assert len(loaded_fps) == 2
        assert loaded_fps[0] != loaded_fps[1]
        assert "session_a" in str(loaded_fps[0])
        assert "session_b" in str(loaded_fps[1])


# ---------------------------------------------------------------------------
# SessionManager.save() — two sessions write different output paths
# ---------------------------------------------------------------------------

class TestSessionManagerSaveUriTemplate:
    """Tests that file-mode outputs resolve to session-specific paths."""

    def _make_sm_with_output(self, session: str, output_dir: Path) -> SessionManager:
        desc = [
            {
                "id": "valence",
                "type": "output",
                "src": "file:annotation:continuous",
                "uri_template": str(output_dir / "{session}" / "valence.annotation"),
                "sample_rate": 30,
                "min_val": -1,
                "max_val": 1,
            }
        ]
        sm = SessionManager(
            dataset="myds",
            data_description=desc,
            session=session,
            source_context={},
        )
        # Seed the output template with a ContinuousAnnotation
        scheme = ContinuousAnnotationScheme(
            name="valence", sample_rate=30, min_val=-1, max_val=1
        )
        sm.output_data_templates["valence"] = ContinuousAnnotation(
            scheme=scheme, data=None
        )
        return sm

    def test_different_sessions_save_different_paths(self, tmp_path):
        saved_fps = []

        def fake_save(data, fp):
            saved_fps.append(fp)
            return True

        with patch(
            "discover_utils.data.handler.file_handler.FileHandler.save",
            side_effect=fake_save,
        ):
            for sess in ("session_a", "session_b"):
                sm = self._make_sm_with_output(sess, tmp_path)
                sm.save()

        assert len(saved_fps) == 2
        assert saved_fps[0] != saved_fps[1]
        assert "session_a" in str(saved_fps[0])
        assert "session_b" in str(saved_fps[1])


# ---------------------------------------------------------------------------
# Output annotation template metadata from desc
# ---------------------------------------------------------------------------

class TestOutputAnnotationMetadata:
    """Tests that annotation templates use metadata from the data description."""

    def _load_output_template(self, desc_override: dict) -> SessionManager:
        """Build a SessionManager that will create an output template from desc."""
        base_desc = {
            "id": "valence",
            "type": "output",
            "src": "file:annotation:continuous",
            "uri_template": "/nonexistent/{session}/valence.annotation",
        }
        base_desc.update(desc_override)
        desc = [base_desc]
        sm = SessionManager(
            dataset="myds",
            data_description=desc,
            session="my_session",
            source_context={},
        )
        # Force a FileNotFoundError so the fallback template is created
        with patch(
            "discover_utils.data.handler.file_handler.FileHandler.load",
            side_effect=FileNotFoundError("not found"),
        ):
            sm.load()
        return sm

    def test_continuous_template_uses_sample_rate_from_desc(self):
        sm = self._load_output_template({"sample_rate": 30, "min_val": -1, "max_val": 1})
        anno = sm.output_data_templates["valence"]
        assert isinstance(anno, ContinuousAnnotation)
        assert anno.annotation_scheme.sample_rate == 30

    def test_continuous_template_uses_min_val_from_desc(self):
        sm = self._load_output_template({"sample_rate": 25, "min_val": -2, "max_val": 2})
        anno = sm.output_data_templates["valence"]
        assert anno.annotation_scheme.min_val == -2

    def test_continuous_template_uses_max_val_from_desc(self):
        sm = self._load_output_template({"sample_rate": 25, "min_val": -2, "max_val": 2})
        anno = sm.output_data_templates["valence"]
        assert anno.annotation_scheme.max_val == 2

    def test_continuous_template_defaults_to_sample_rate_1(self):
        sm = self._load_output_template({})
        anno = sm.output_data_templates["valence"]
        assert anno.annotation_scheme.sample_rate == 1

    def test_discrete_template_uses_classes_from_desc(self):
        classes = {"0": "neutral", "1": "happiness", "2": "sadness"}
        desc_override = {
            "id": "expression",
            "src": "file:annotation:discrete",
            "classes": classes,
        }
        sm = self._load_output_template(desc_override)
        # Key is "expression" because we overrode id
        anno = sm.output_data_templates["expression"]
        assert isinstance(anno, DiscreteAnnotation)
        assert anno.annotation_scheme.classes == classes

    def test_discrete_template_defaults_when_no_classes_in_desc(self):
        desc_override = {
            "id": "expr2",
            "src": "file:annotation:discrete",
        }
        sm = self._load_output_template(desc_override)
        anno = sm.output_data_templates["expr2"]
        assert isinstance(anno, DiscreteAnnotation)
        # Default classes should be present
        assert len(anno.annotation_scheme.classes) > 0
