from __future__ import annotations

from pathlib import Path

from model_audit_cli.adapters.repo_view import RepoView


def test_repo_view_basic(tmp_path: Path) -> None:
    """Test basic functionality of the `RepoView` class."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# hello\n", encoding="utf-8")
    (root / "config.json").write_text('{"x": 1}', encoding="utf-8")

    view = RepoView(root)
    assert view.exists("README.md")
    assert view.read_text("README.md").startswith("# hello")
    assert view.read_json("config.json")["x"] == 1
    assert view.size_bytes("README.md") > 0
    assert [p.name for p in view.glob("*.md")] == ["README.md"]
