from typing import Optional

from models import Model
from resources.code_resource import CodeResource
from resources.dataset_resource import DatasetResource
from resources.model_resource import ModelResource


class URLHandler:
    """Handler for processing URLs and creating Model instances from file input."""

    def get_models(self, filename: str) -> list[Model]:
        """Parse URLs from a file and create Model instances.

        Reads a file containing comma-separated URLs on each line, where each line
        represents a model with the format: code_url,dataset_url,model_url.

        Args:
            filename (str): Path to the file containing URL data. Each line should
                contain three comma-separated URLs in the format:
                code_url,dataset_url,model_url

        Returns:
            list[Model]: A list of Model instances created from the parsed URLs.
        """
        with open(filename, "r") as file:
            content = file.readlines()
            model_urls_list = []
            for line in content:
                urls = line.strip("\n").split(",")
                urls = [url.strip() for url in urls]
                model_urls_list.append(urls)

        models = []
        for model_urls in model_urls_list:
            model_resource = ModelResource(url=model_urls[2])
            data_resource = (
                DatasetResource(url=model_urls[1]) if model_urls[1] else None
            )
            code_resource = CodeResource(url=model_urls[0]) if model_urls[0] else None

            model = Model(
                model=model_resource, dataset=data_resource, code=code_resource
            )
            models.append(model)

        return models

    def check_for_shared_dataset(
        self, curr_model: Model, prev_model: Model
    ) -> Optional[DatasetResource]:
        """Check if the current model shares a dataset with the previous model.

        This method examines the README.md file of the current model to determine
        if it references the same dataset as the previous model. If a match is found,
        it returns the shared DatasetResource.

        Args:
            curr_model (Model): The current model to check for dataset sharing.
            prev_model (Model): The previous model whose dataset to compare against.

        Returns:
            Optional[DatasetResource]: The shared Dataset if found, None otherwise.
        """
        if not prev_model.dataset:
            return None

        with curr_model.model.open_files(["README.md"]) as repo:
            if repo.exists("README.md"):
                readme_content = repo.read_text("README.md")
                if prev_model.dataset.url in readme_content:
                    return prev_model.dataset

        return None


if __name__ == "__main__":
    handler = URLHandler()
    models = handler.get_models("urls.txt")
    print(handler.check_for_shared_dataset(models[1], models[0]))
