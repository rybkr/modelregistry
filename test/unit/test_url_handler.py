from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from models import Model
from resources.dataset_resource import DatasetResource
from resources.model_resource import ModelResource
from url_handler import URLHandler


class TestURLHandler:
    """Test cases for the URLHandler class."""

    def test_get_models_parses_file_and_builds_models(self, tmp_path: Path) -> None:
        """Ensure get_models constructs Model instances from CSV-style file."""
        file_path = tmp_path / "urls.txt"
        file_path.write_text(
            " https://github.com/org/repo , https://huggingface.co/datasets/org/data ,"
            " https://huggingface.co/org/model\n"
            "https://gitlab.com/org/repo2,,https://huggingface.co/org/model2\n"
        )

        handler = URLHandler()

        models = handler.get_models(str(file_path))

        assert len(models) == 2

        first, second = models
        assert first.code is not None
        assert first.code.url == "https://github.com/org/repo"
        assert first.dataset is not None
        assert first.dataset.url == "https://huggingface.co/datasets/org/data"
        assert first.model.url == "https://huggingface.co/org/model"

        assert second.code is not None
        assert second.code.url == "https://gitlab.com/org/repo2"
        assert second.dataset is None
        assert second.model.url == "https://huggingface.co/org/model2"

    def test_check_for_shared_dataset_returns_dataset(self) -> None:
        """Return previous dataset when README references it."""
        handler = URLHandler()
        shared_dataset = DatasetResource("https://huggingface.co/datasets/org/data")
        prev_model = Model(
            model=ModelResource("https://huggingface.co/org/prev"),
            dataset=shared_dataset,
            code=None,
        )
        curr_model = Model(
            model=ModelResource("https://huggingface.co/org/current"),
            dataset=None,
            code=None,
        )

        repo_view = MagicMock()
        repo_view.exists.return_value = True
        repo_view.read_text.return_value = (
            "This model builds upon https://huggingface.co/datasets/org/data dataset."
        )

        @contextmanager
        def fake_open_files(self, allow_patterns=None):
            assert allow_patterns == ["README.md"]
            yield repo_view

        with patch.object(ModelResource, "open_files", fake_open_files):
            result = handler.check_for_shared_dataset(curr_model, prev_model)

        assert result is shared_dataset
        repo_view.exists.assert_called_once_with("README.md")
        repo_view.read_text.assert_called_once_with("README.md")

    def test_check_for_shared_dataset_returns_none_without_readme_reference(
        self,
    ) -> None:
        """Return None when README is missing or lacks the dataset URL."""
        handler = URLHandler()
        prev_model = Model(
            model=ModelResource("https://huggingface.co/org/prev"),
            dataset=DatasetResource("https://huggingface.co/datasets/org/data"),
            code=None,
        )
        curr_model = Model(
            model=ModelResource("https://huggingface.co/org/current"),
            dataset=None,
            code=None,
        )

        repo_view = MagicMock()
        repo_view.exists.return_value = False

        @contextmanager
        def fake_open_files(self, allow_patterns=None):
            yield repo_view

        with patch.object(ModelResource, "open_files", fake_open_files):
            result = handler.check_for_shared_dataset(curr_model, prev_model)

        assert result is None
        repo_view.exists.assert_called_once_with("README.md")
        repo_view.read_text.assert_not_called()
