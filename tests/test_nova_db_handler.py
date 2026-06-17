"""Tests for NovaDBHandler exploration queries and the optimized annotation load path.

Mock-based (unittest.mock), matching the style of test_file_uri_resolution.py. These tests
validate the *call shape* of the queries (which collection, which field/projection/pipeline,
how results are mapped) - they do not exercise real MongoDB semantics. Equivalence of the
optimized _load_annotation against the old aggregate pipeline is verified manually against a
real database.
"""

from unittest.mock import MagicMock

import pytest

from discover_utils.data.handler.nova_db_handler import (
    NovaDBHandler,
    AnnotationHandler,
    SCHEME_COLLECTION,
    ROLE_COLLECTION,
    ANNOTATOR_COLLECTION,
    STREAM_COLLECTION,
    SESSION_COLLECTION,
    ANNOTATION_COLLECTION,
    ANNOTATION_DATA_COLLECTION,
)


def _make_handler(handler_cls=NovaDBHandler):
    """Build a handler whose client[dataset][collection] returns a stable per-collection mock.

    Returns (handler, client, collections, db) where `collections` is a dict lazily populated
    with one MagicMock per collection name accessed and `db` is the client[dataset] mock.
    """
    handler = handler_cls()
    collections = {}
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: collections.setdefault(name, MagicMock())
    client = MagicMock()
    client.__getitem__.return_value = db
    handler._client = client
    return handler, client, collections, db


# ---------------------------------------------------------------------------
# Connection guard
# ---------------------------------------------------------------------------

class TestRequireClient:
    def test_raises_when_not_connected(self):
        handler = NovaDBHandler()  # no connection params -> _client stays None
        with pytest.raises(ConnectionError):
            handler.list_roles("ds")


# ---------------------------------------------------------------------------
# list_datasets
# ---------------------------------------------------------------------------

class TestListDatasets:
    def test_filters_system_dbs_and_non_nova(self):
        handler = NovaDBHandler()
        client = MagicMock()
        client.list_database_names.return_value = ["admin", "config", "local", "nova_ds", "other"]

        nova_db = MagicMock()
        nova_db.list_collection_names.return_value = [SESSION_COLLECTION, SCHEME_COLLECTION]
        other_db = MagicMock()
        other_db.list_collection_names.return_value = ["something_else"]
        client.__getitem__.side_effect = lambda name: {"nova_ds": nova_db, "other": other_db}[name]
        handler._client = client

        result = handler.list_datasets()  # nova_only=True default
        assert result == ["nova_ds"]

    def test_nova_only_false_keeps_all_non_system(self):
        handler = NovaDBHandler()
        client = MagicMock()
        client.list_database_names.return_value = ["admin", "config", "local", "nova_ds", "other"]
        handler._client = client

        result = handler.list_datasets(nova_only=False)
        assert result == ["nova_ds", "other"]
        # must not probe collections when nova_only is False
        client.__getitem__.assert_not_called()


# ---------------------------------------------------------------------------
# distinct-based enumeration
# ---------------------------------------------------------------------------

class TestDistinctEnumeration:
    @pytest.mark.parametrize(
        "method, collection",
        [
            ("list_sessions", SESSION_COLLECTION),
            ("list_scheme_names", SCHEME_COLLECTION),
            ("list_roles", ROLE_COLLECTION),
            ("list_annotators", ANNOTATOR_COLLECTION),
        ],
    )
    def test_distinct_on_name(self, method, collection):
        handler, client, collections, db = _make_handler()
        coll_mock = collections.setdefault(collection, MagicMock())
        coll_mock.distinct.return_value = ["a", "b"]

        result = getattr(handler, method)("ds")

        client.__getitem__.assert_called_with("ds")
        coll_mock.distinct.assert_called_once_with("name")
        assert result == ["a", "b"]


# ---------------------------------------------------------------------------
# projection-based metadata listing
# ---------------------------------------------------------------------------

class TestMetadataListing:
    def test_list_schemes_projection(self):
        handler, client, collections, db = _make_handler()
        coll = collections.setdefault(SCHEME_COLLECTION, MagicMock())
        coll.find.return_value = [{"name": "transcript", "type": "FREE"}]

        result = handler.list_schemes("ds")

        coll.find.assert_called_once_with({}, {"name": 1, "type": 1, "_id": 0})
        assert result == [{"name": "transcript", "type": "FREE"}]

    def test_list_streams_metadata_only(self):
        handler, client, collections, db = _make_handler()
        coll = collections.setdefault(STREAM_COLLECTION, MagicMock())
        coll.find.return_value = [{"name": "audio", "type": "feature", "sr": 16000}]

        result = handler.list_streams("ds")

        args, _ = coll.find.call_args
        assert args[0] == {}
        projection = args[1]
        # metadata fields projected, no file payload
        assert projection["name"] == 1 and projection["sr"] == 1 and projection["dimlabels"] == 1
        assert result == [{"name": "audio", "type": "feature", "sr": 16000}]


# ---------------------------------------------------------------------------
# list_annotations - metadata-only aggregate (no AnnotationData lookup)
# ---------------------------------------------------------------------------

class TestListAnnotations:
    def _pipeline_of(self, collections):
        coll = collections[ANNOTATION_COLLECTION]
        (pipeline,), _ = coll.aggregate.call_args
        return pipeline

    def test_omits_annotation_data_lookup(self):
        handler, client, collections, db = _make_handler()
        coll = collections.setdefault(ANNOTATION_COLLECTION, MagicMock())
        coll.aggregate.return_value = [
            {"session": "s1", "annotator": "a", "role": "r", "scheme": "sc",
             "isFinished": True, "isLocked": False}
        ]

        result = handler.list_annotations("ds")

        pipeline = self._pipeline_of(collections)
        lookups = [s["$lookup"]["from"] for s in pipeline if "$lookup" in s]
        assert lookups == [SESSION_COLLECTION, ANNOTATOR_COLLECTION, ROLE_COLLECTION, SCHEME_COLLECTION]
        assert ANNOTATION_DATA_COLLECTION not in lookups  # the lazy-load win
        # no session filter -> no $match stage
        assert not any("$match" in s for s in pipeline)
        assert result[0]["scheme"] == "sc"

    def test_session_filter_matches_session_id_before_lookups(self):
        handler, client, collections, db = _make_handler()
        collections.setdefault(SESSION_COLLECTION, MagicMock()).find_one.return_value = {"_id": "sess1"}
        coll = collections.setdefault(ANNOTATION_COLLECTION, MagicMock())
        coll.aggregate.return_value = []

        handler.list_annotations("ds", session="s1")

        pipeline = self._pipeline_of(collections)
        # session_id $match must be the FIRST stage, before any $lookup (prunes the join)
        assert pipeline[0] == {"$match": {"session_id": "sess1"}}
        collections[SESSION_COLLECTION].find_one.assert_called_once_with({"name": "s1"}, {"_id": 1})

    def test_unknown_session_returns_empty(self):
        handler, client, collections, db = _make_handler()
        collections.setdefault(SESSION_COLLECTION, MagicMock()).find_one.return_value = None
        anno = collections.setdefault(ANNOTATION_COLLECTION, MagicMock())

        result = handler.list_annotations("ds", session="missing")

        assert result == []
        anno.aggregate.assert_not_called()


# ---------------------------------------------------------------------------
# _load_annotation optimization (id-resolution instead of collection-wide $lookup)
# ---------------------------------------------------------------------------

class TestLoadAnnotationOptimized:
    def _seed_ids(self, collections):
        collections.setdefault(SCHEME_COLLECTION, MagicMock()).find_one.return_value = {"_id": "scheme1"}
        collections.setdefault(SESSION_COLLECTION, MagicMock()).find_one.return_value = {"_id": "sess1"}
        collections.setdefault(ROLE_COLLECTION, MagicMock()).find_one.return_value = {"_id": "role1"}
        collections.setdefault(ANNOTATOR_COLLECTION, MagicMock()).find_one.return_value = {"_id": "ann1"}

    def test_default_resolves_ids_then_fetches_data_and_scheme(self):
        handler, client, collections, db = _make_handler(AnnotationHandler)
        self._seed_ids(collections)
        anno_coll = collections.setdefault(ANNOTATION_COLLECTION, MagicMock())
        anno_coll.find_one.return_value = {"_id": "anno1", "data_id": "data1"}
        data_coll = collections.setdefault(ANNOTATION_DATA_COLLECTION, MagicMock())
        data_coll.find_one.return_value = {"_id": "data1", "labels": [1, 2, 3]}

        result = handler._load_annotation("ds", "sess", "ann", "role", "scheme")

        # names resolved by indexed find_one on the right collections (ids only)
        collections[SCHEME_COLLECTION].find_one.assert_any_call({"name": "scheme"}, {"_id": 1})
        # full scheme doc fetched by id on the non-projected path
        collections[SCHEME_COLLECTION].find_one.assert_any_call({"_id": "scheme1"})
        collections[SESSION_COLLECTION].find_one.assert_called_with({"name": "sess"}, {"_id": 1})
        collections[ROLE_COLLECTION].find_one.assert_called_with({"name": "role"}, {"_id": 1})
        collections[ANNOTATOR_COLLECTION].find_one.assert_called_with({"name": "ann"}, {"_id": 1})
        # annotation fetched by the four ids
        anno_coll.find_one.assert_called_once_with(
            {"session_id": "sess1", "annotator_id": "ann1", "role_id": "role1", "scheme_id": "scheme1"}
        )
        # AnnotationData payload fetched only for the matched annotation
        data_coll.find_one.assert_called_once_with({"_id": "data1"})
        # caller contract: data/scheme as single-item lists
        assert result["data"] == [{"_id": "data1", "labels": [1, 2, 3]}]
        assert result["scheme"] == [{"_id": "scheme1"}]

    def test_project_skips_data_and_scheme_fetch(self):
        handler, client, collections, db = _make_handler(AnnotationHandler)
        self._seed_ids(collections)
        anno_coll = collections.setdefault(ANNOTATION_COLLECTION, MagicMock())
        anno_coll.find_one.return_value = {"_id": "anno1", "isLocked": False, "data_id": "data1"}
        data_coll = collections.setdefault(ANNOTATION_DATA_COLLECTION, MagicMock())

        project = {"_id": 1, "isLocked": 1, "data_id": 1}
        result = handler._load_annotation("ds", "sess", "ann", "role", "scheme", project=project)

        anno_coll.find_one.assert_called_once_with(
            {"session_id": "sess1", "annotator_id": "ann1", "role_id": "role1", "scheme_id": "scheme1"},
            project,
        )
        data_coll.find_one.assert_not_called()
        assert "data" not in result and "scheme" not in result
        assert result == {"_id": "anno1", "isLocked": False, "data_id": "data1"}

    def test_missing_name_returns_empty(self):
        handler, client, collections, db = _make_handler(AnnotationHandler)
        self._seed_ids(collections)
        collections[ROLE_COLLECTION].find_one.return_value = None  # role does not exist

        result = handler._load_annotation("ds", "sess", "ann", "role", "scheme")

        assert result == {}
        # must not attempt to fetch the annotation if a name did not resolve
        collections.setdefault(ANNOTATION_COLLECTION, MagicMock()).find_one.assert_not_called()
