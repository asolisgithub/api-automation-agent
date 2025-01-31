import json
import logging
import os
from typing import List, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from src.ai_tools.models.file_reading_input import FileReadingInput

from .models.file_spec import FileSpec

from ..configuration.config import Config
from ..utils.logger import Logger
from ..services.file_service import FileService


class FileReadingTool(BaseTool):
    name: str = "read_files"
    description: str = (
        "Reads the content of all files specified by path and returns the concat of all contents"
    )
    args_schema: Type[BaseModel] = FileReadingInput
    config: Config = None
    file_service: FileService = None
    logger: logging.Logger = None

    def __init__(self, config: Config, file_service: FileService):
        super().__init__()
        self.config = config
        self.file_service = file_service
        self.logger = Logger.get_logger(__name__)

    def _run(self, files: List[str]) -> List[FileSpec]:
        all_read_files = []

        for file_path in files:
            try:
                fileSpec = {
                    "path": file_path,
                    "fileContent": self.file_service.read_file(
                        os.path.join(self.config.destination_folder, file_path)
                    ),
                }

                all_read_files.append(fileSpec)

            except Exception as e:
                self.logger.error(f"Error reading file: {e}")

        self.logger.info(f"Successfully read {len(files)} files")
        return all_read_files

    async def _arun(self, files: List[str]) -> str:
        return self._run(files)
