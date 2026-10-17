import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../mcp-server"))
)

import server as mcp_server

# n1 --refers-to--> n2
# n1 --calls------> n3 --references--> n5
# n1 --related-to-> n4
EDGES = [
    {"from": "n1", "to": "n2", "type": "refers-to"},
    {"from": "n1", "to": "n3", "type": "calls"},
    {"from": "n1", "to": "n4", "type": "related-to"},
    {"from": "n3", "to": "n5", "type": "references"},
]


def _make_kb():
    adj: dict[str, list[dict]] = {}
    for e in EDGES:
        adj.setdefault(e["from"], []).append(e)
    nodes = {
        f"n{i}": {
            "id": f"n{i}",
            "label": f"node {i}",
            "type": "section",
            "chunk_id": f"c{i}",
            "category": ["concept"],
            "entrypoint": i == 1,
        }
        for i in range(1, 6)
    }
    chunks = {
        f"c{i}": {
            "id": f"c{i}",
            "text": f"text {i}",
            "file_path": f"docs/{i}.md",
            "section": f"S{i}",
        }
        for i in range(1, 6)
    }
    return {
        "nodes": nodes,
        "edges": EDGES,
        "adj": adj,
        "chunks": chunks,
        "chunk_to_nodes": {f"c{i}": [f"n{i}"] for i in range(1, 6)},
    }


def _hits():
    return [{"chunk_id": "c1", "score": 1.0}]


def _downstream_ids(result):
    return {d["node_id"] for d in result["downstream"]}


class TestImpactAnalysisEdgeTypes:
    def test_default_follows_every_edge_and_adds_no_key(self):
        with patch.object(mcp_server, "load_kb", return_value=_make_kb()):
            result = mcp_server.impact_analysis("n1")
        assert _downstream_ids(result) == {"n2", "n3", "n4", "n5"}
        assert "edge_types" not in result

    def test_allow_list_restricts_traversal(self):
        with patch.object(mcp_server, "load_kb", return_value=_make_kb()):
            result = mcp_server.impact_analysis("n1", edge_types=["calls"])
        assert _downstream_ids(result) == {"n3"}
        assert result["edge_types"] == ["calls"]

    def test_allow_list_with_two_types_reaches_through_both(self):
        with patch.object(mcp_server, "load_kb", return_value=_make_kb()):
            result = mcp_server.impact_analysis(
                "n1", edge_types=["calls", "references"]
            )
        assert _downstream_ids(result) == {"n3", "n5"}

    def test_types_are_case_insensitive(self):
        with patch.object(mcp_server, "load_kb", return_value=_make_kb()):
            result = mcp_server.impact_analysis("n1", edge_types=["CALLS"])
        assert _downstream_ids(result) == {"n3"}

    def test_empty_list_follows_no_edge(self):
        with patch.object(mcp_server, "load_kb", return_value=_make_kb()):
            result = mcp_server.impact_analysis("n1", edge_types=[])
        assert result["downstream"] == []
        assert result["edge_types"] == []

    def test_unknown_type_follows_no_edge(self):
        with patch.object(mcp_server, "load_kb", return_value=_make_kb()):
            result = mcp_server.impact_analysis("n1", edge_types=["no-such-type"])
        assert result["downstream"] == []


class TestFocusPackEdgeTypes:
    def _run(self, **kwargs):
        with (
            patch.object(mcp_server, "load_kb", return_value=_make_kb()),
            patch.object(mcp_server, "search_query", return_value=_hits()),
        ):
            return mcp_server.focus_pack("anything", **kwargs)

    def test_default_follows_every_edge_and_adds_no_key(self):
        result = self._run(depth=2)
        assert set(result["related_nodes"]) == {"n1", "n2", "n3", "n4", "n5"}
        assert "edge_types" not in result

    def test_allow_list_restricts_expansion(self):
        result = self._run(depth=1, edge_types=["calls"])
        assert set(result["related_nodes"]) == {"n1", "n3"}
        assert result["edge_types"] == ["calls"]

    def test_allow_list_follows_chain_over_depth(self):
        result = self._run(depth=2, edge_types=["calls", "references"])
        assert set(result["related_nodes"]) == {"n1", "n3", "n5"}

    def test_filtered_expansion_drops_the_chunks_of_unfollowed_nodes(self):
        result = self._run(depth=2, edge_types=["calls"])
        assert "c2" not in result["chunks"]
        assert "c3" in result["chunks"]

    def test_empty_list_keeps_only_the_primary_nodes(self):
        result = self._run(depth=2, edge_types=[])
        assert set(result["related_nodes"]) == {"n1"}


class TestGuidedPathEdgeTypes:
    def _run(self, **kwargs):
        with (
            patch.object(mcp_server, "load_kb", return_value=_make_kb()),
            patch.object(mcp_server, "search_query", return_value=_hits()),
        ):
            return mcp_server.guided_path("anything", **kwargs)

    @staticmethod
    def _path_ids(result):
        return {step["node_id"] for step in result["path"]}

    def test_default_follows_every_edge_and_adds_no_key(self):
        result = self._run()
        assert self._path_ids(result) == {"n1", "n2", "n3", "n4", "n5"}
        assert "edge_types" not in result

    def test_allow_list_restricts_the_path(self):
        result = self._run(edge_types=["calls", "references"])
        assert self._path_ids(result) == {"n1", "n3", "n5"}
        assert result["edge_types"] == ["calls", "references"]
