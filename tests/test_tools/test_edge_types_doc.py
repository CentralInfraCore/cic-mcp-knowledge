import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from make_source import EDGE_TYPE_DESCRIPTIONS, generate_edge_types_doc


def _doc(tmp_path, edge_types):
    edges = {f"e{i}": {"type": t} for i, t in enumerate(edge_types)}
    generate_edge_types_doc({"edges": edges}, output_dir=str(tmp_path))
    return (tmp_path / "edge_types.md").read_text(encoding="utf-8")


def test_lists_every_type_that_occurs_exactly_once(tmp_path):
    doc = _doc(
        tmp_path, ["calls", "related-to", "related-to", "references", "refers-to"]
    )
    for edge_type in ("calls", "related-to", "references", "refers-to"):
        assert doc.count(f"- `{edge_type}`:") == 1


def test_describes_each_known_type(tmp_path):
    doc = _doc(tmp_path, list(EDGE_TYPE_DESCRIPTIONS))
    for edge_type, description in EDGE_TYPE_DESCRIPTIONS.items():
        assert f"- `{edge_type}`: {description}" in doc


def test_unknown_type_is_listed_with_a_placeholder(tmp_path):
    doc = _doc(tmp_path, ["brand-new"])
    assert "- `brand-new`: no description registered for this type." in doc


def test_output_is_independent_of_edge_counts(tmp_path):
    few = _doc(tmp_path, ["calls"])
    many = _doc(tmp_path, ["calls"] * 50)
    assert few == many


def test_every_type_the_graph_builder_emits_has_a_description():
    # build_knowledge_base() emits exactly these four types (see create_knowledge_graph_with_content)
    assert set(EDGE_TYPE_DESCRIPTIONS) == {
        "refers-to",
        "related-to",
        "references",
        "calls",
    }
