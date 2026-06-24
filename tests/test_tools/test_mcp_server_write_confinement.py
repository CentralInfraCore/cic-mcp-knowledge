"""Write-confinement tests for update_companion() / record_decision().

Covers the path-traversal fix in mcp-server/server.py:
- _resolve_within_source_dir() must reject any file_path/companion_path that
  resolves outside SOURCE_DIR (no write/read attempted), for BOTH
  update_companion() and record_decision().
- Legitimate, SOURCE_DIR-confined paths must keep working (no regression).
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../mcp-server")))

import server as mcp_server  # noqa: E402


@pytest.fixture
def source_dir(tmp_path, monkeypatch):
    """Confine SOURCE_DIR to an isolated tmp directory for the duration of the test."""
    sd = tmp_path / "source"
    sd.mkdir()
    monkeypatch.setattr(mcp_server, "SOURCE_DIR", sd)
    return sd


@pytest.fixture
def outside_file(tmp_path):
    """A file OUTSIDE source_dir's tree, with valid YAML content (mapping)."""
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    victim = outside_dir / "victim.yaml"
    victim.write_text("description: original-untouched-content\n")
    return victim


@pytest.fixture
def legit_companion(source_dir):
    """A companion YAML INSIDE source_dir."""
    companion = source_dir / "pkg" / "module.yaml"
    companion.parent.mkdir(parents=True)
    companion.write_text("description: original\ncategory: []\nused_in: []\nrelated_nodes: []\ntags: []\n")
    return companion


# ---------------------------------------------------------------------------
# _resolve_within_source_dir — helper unit tests
# ---------------------------------------------------------------------------

class TestResolveWithinSourceDir:
    def test_rejects_absolute_path_outside_source_dir(self, source_dir, outside_file):
        with pytest.raises(ValueError):
            mcp_server._resolve_within_source_dir(str(outside_file))

    def test_rejects_dotdot_traversal(self, source_dir):
        traversal = str(source_dir / ".." / "etc" / "passwd")
        with pytest.raises(ValueError):
            mcp_server._resolve_within_source_dir(traversal)

    def test_accepts_relative_path_inside_source_dir(self, source_dir, legit_companion):
        rel = str(legit_companion.relative_to(source_dir))
        resolved = mcp_server._resolve_within_source_dir(rel)
        assert resolved == legit_companion.resolve()

    def test_accepts_absolute_path_inside_source_dir(self, source_dir, legit_companion):
        resolved = mcp_server._resolve_within_source_dir(str(legit_companion))
        assert resolved == legit_companion.resolve()


# ---------------------------------------------------------------------------
# update_companion() — rejection (path traversal refused, no write happens)
# ---------------------------------------------------------------------------

class TestUpdateCompanionRejection:
    def test_rejects_outside_source_dir_absolute_path(self, source_dir, outside_file):
        before = outside_file.read_text()
        result = mcp_server.update_companion(
            file_path=str(outside_file),
            description="PWNED",
        )
        assert result["success"] is False
        assert "escapes SOURCE_DIR" in result["message"]
        # File must be completely untouched -- no write attempted.
        assert outside_file.read_text() == before
        assert "PWNED" not in outside_file.read_text()


# ---------------------------------------------------------------------------
# update_companion() — no regression (legitimate, in-SOURCE_DIR write still works)
# ---------------------------------------------------------------------------

class TestUpdateCompanionNoRegression:
    def test_updates_legit_companion_inside_source_dir(self, source_dir, legit_companion):
        result = mcp_server.update_companion(
            file_path=str(legit_companion),
            description="updated description",
        )
        assert result["success"] is True
        assert "description" in result["updated_fields"]
        assert "updated description" in legit_companion.read_text()

    def test_updates_legit_companion_via_relative_path(self, source_dir, legit_companion):
        rel = str(legit_companion.relative_to(source_dir))
        result = mcp_server.update_companion(
            file_path=rel,
            description="updated via relative path",
        )
        assert result["success"] is True
        assert "updated via relative path" in legit_companion.read_text()


# ---------------------------------------------------------------------------
# record_decision() — rejection (path traversal refused, no write happens)
# ---------------------------------------------------------------------------

class TestRecordDecisionRejection:
    def test_rejects_outside_source_dir_companion_path(self, source_dir, outside_file):
        before = outside_file.read_text()
        kb = {"nodes": {}}
        with patch.object(mcp_server, "load_kb", return_value=kb):
            result = mcp_server.record_decision(
                node_id="n1",
                decision="PWNED decision",
                companion_path=str(outside_file),
            )
        assert result["success"] is False
        assert "escapes SOURCE_DIR" in result["message"]
        assert outside_file.read_text() == before
        assert "PWNED" not in outside_file.read_text()


# ---------------------------------------------------------------------------
# record_decision() — no regression (legitimate, in-SOURCE_DIR write still works)
# ---------------------------------------------------------------------------

class TestRecordDecisionNoRegression:
    def test_records_decision_in_legit_companion(self, source_dir, legit_companion):
        kb = {"nodes": {}}
        with patch.object(mcp_server, "load_kb", return_value=kb):
            result = mcp_server.record_decision(
                node_id="n1",
                decision="adopt confinement check",
                rationale="prevent path traversal",
                companion_path=str(legit_companion),
            )
        assert result["success"] is True
        content = legit_companion.read_text()
        assert "adopt confinement check" in content
        assert "agent_decisions" in content

    def test_records_decision_via_relative_companion_path(self, source_dir, legit_companion):
        rel = str(legit_companion.relative_to(source_dir))
        kb = {"nodes": {}}
        with patch.object(mcp_server, "load_kb", return_value=kb):
            result = mcp_server.record_decision(
                node_id="n2",
                decision="relative path still works",
                companion_path=rel,
            )
        assert result["success"] is True
        assert "relative path still works" in legit_companion.read_text()
