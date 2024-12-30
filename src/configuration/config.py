from enum import Enum
from dataclasses import dataclass
from typing import Any

from .models import Model


class Envs(Enum):
    PROD = "PROD"
    DEV = "DEV"


class GenerationOptions(Enum):
    MODELS = "models"
    MODELS_AND_FIRST_TEST = "models_and_first_test"
    MODELS_AND_TESTS = "models_and_tests"


@dataclass
class Config:
    env: Envs = Envs.DEV
    debug: bool = False
    model: Model = Model.CLAUDE_HAIKU
    generate: GenerationOptions = GenerationOptions.MODELS_AND_FIRST_TEST
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    api_file_path: str = ""
    destination_folder: str = ""
    endpoint: str = ""
    source: str = ""
    use_existing_framework: bool = False

    def update(self, updates: dict[str, Any]):
        for key, value in updates.items():
            setattr(self, key, value)
