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

    def test_escaped_braces_in_template_do_not_count_as_placeholders(self):
        # ``{{`` and ``}}`` are literal braces in a format string. They must not
        # trigger the dataset/session placeholder validation.
        desc = {"uri_template": "/data/{{dataset}}/{{session}}/file.mp4"}
        result = resolve_file_uri(desc, dataset=None, session=None)
        assert result == Path("/data/{dataset}/{session}/file.mp4")

    def test_format_specs_on_placeholders_are_recognized(self):
        # ``{session:>8}`` is a valid placeholder with a format spec; substring
        # checks would miss it. The Formatter-based detection must catch it.
        desc = {"uri_template": "/data/{session:>8}/file.mp4"}
        with pytest.raises(ValueError):
            resolve_file_uri(desc, dataset="ds", session=None)


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

    def test_discrete_template_uses_classes_from_desc_canonical(self):
        classes = {
            "0": {"name": "neutral", "color": "#888"},
            "1": {"name": "happiness"},
        }
        desc_override = {
            "id": "expression",
            "src": "file:annotation:discrete",
            "classes": classes,
        }
        sm = self._load_output_template(desc_override)
        anno = sm.output_data_templates["expression"]
        assert isinstance(anno, DiscreteAnnotation)
        assert anno.annotation_scheme.classes == classes

    def test_discrete_template_normalizes_legacy_string_classes(self):
        legacy = {"0": "neutral", "1": "happiness", "2": "sadness"}
        desc_override = {
            "id": "expression",
            "src": "file:annotation:discrete",
            "classes": legacy,
        }
        sm = self._load_output_template(desc_override)
        anno = sm.output_data_templates["expression"]
        assert isinstance(anno, DiscreteAnnotation)
        assert anno.annotation_scheme.classes == {
            "0": {"name": "neutral"},
            "1": {"name": "happiness"},
            "2": {"name": "sadness"},
        }

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


# ---------------------------------------------------------------------------
# FileHandler.save() — discrete scheme XML id-injection
# ---------------------------------------------------------------------------

class TestDiscreteSchemeIdInjection:
    """Verifies that the writer injects the canonical class id from the outer
    dict key into the XML, so callers don't need to repeat it inside the
    per-class attribute dict."""

    def _save_and_parse(self, classes: dict, tmp_path: Path):
        import numpy as np
        import xml.etree.ElementTree as Et
        from discover_utils.data.handler.file_handler import FileHandler

        scheme = DiscreteAnnotationScheme(name="emotion", classes=classes)
        data = np.array([], dtype=scheme.label_dtype)
        anno = DiscreteAnnotation(data=data, scheme=scheme)
        fp = tmp_path / "out.annotation"
        FileHandler().save(data=anno, fp=fp)
        # The XML lives at fp; the binary data lives at fp + "~"
        return Et.parse(fp).getroot()

    def test_id_injected_from_outer_key_when_missing_inside(self, tmp_path):
        classes = {
            "0": {"name": "neutral"},
            "1": {"name": "happiness", "color": "#ffd700"},
        }
        root = self._save_and_parse(classes, tmp_path)
        items = root.findall("./scheme/item")
        assert {it.get("id"): it.get("name") for it in items} == {
            "0": "neutral",
            "1": "happiness",
        }
        color_by_id = {it.get("id"): it.get("color") for it in items}
        assert color_by_id["1"] == "#ffd700"

    def test_outer_key_wins_over_inner_id(self, tmp_path):
        # If the inner dict carries a (potentially stale) id, the outer key
        # must win — the outer dict is the single source of truth.
        classes = {
            "0": {"id": "999", "name": "neutral"},
            "1": {"id": "888", "name": "happiness"},
        }
        root = self._save_and_parse(classes, tmp_path)
        ids = sorted(it.get("id") for it in root.findall("./scheme/item"))
        assert ids == ["0", "1"]

    def test_legacy_string_classes_are_coerced_and_serialize(self, tmp_path):
        # Legacy {id: name_str} form should be normalized at scheme construction
        # and round-trip cleanly through the writer.
        classes = {"0": "neutral", "1": "happiness"}
        root = self._save_and_parse(classes, tmp_path)
        assert {it.get("id"): it.get("name") for it in root.findall("./scheme/item")} == {
            "0": "neutral",
            "1": "happiness",
        }
