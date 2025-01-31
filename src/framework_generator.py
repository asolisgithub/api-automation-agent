import copy
import re
from typing import Optional, List, Dict, Any

from .configuration.config import Config, GenerationOptions
from .processors.swagger_processor import SwaggerProcessor
from .processors.postman_processor import PostmanProcessor
from .services.command_service import CommandService
from .services.file_service import FileService
from .services.llm_service import LLMService
from .utils.logger import Logger
from .utils.constants import DataSource


class FrameworkGenerator:
    def __init__(
        self,
        config: Config,
        llm_service: LLMService,
        command_service: CommandService,
        file_service: FileService,
        swagger_processor: SwaggerProcessor,
        postman_processor: PostmanProcessor,
    ):
        self.config = config
        self.llm_service = llm_service
        self.command_service = command_service
        self.file_service = file_service
        self.swagger_processor = swagger_processor
        self.postman_processor = postman_processor
        self.models_count = 0
        self.tests_count = 0
        self.logger = Logger.get_logger(__name__)

    def _log_error(self, message: str, exc: Exception):
        """Helper method to log errors consistently"""
        self.logger.error(f"{message}: {exc}")

    def process_api_definition(self) -> List[Dict[str, Any]]:
        """Process the API definition file and return a list of API endpoints"""
        try:
            self.logger.info(
                f"\nProcessing API definition from {self.config.api_file_path}"
            )

            if self.config.source == DataSource.POSTMAN:
                return self.postman_processor.process_json(self.config.api_file_path)
            else:
                return self.swagger_processor.process_api_definition(
                    self.config.api_file_path
                )
        except Exception as e:
            self._log_error("Error processing API definition", e)
            raise

    def setup_framework(self):
        """Set up the framework environment"""
        try:
            self.logger.info(
                f"\nSetting up framework in {self.config.destination_folder}"
            )
            self.file_service.copy_framework_template(self.config.destination_folder)
            self.command_service.install_dependencies()
        except Exception as e:
            self._log_error("Error setting up framework", e)
            raise

    def create_env_file(self, api_definition):
        """Generate the .env file from the provided API definition"""
        try:
            self.logger.info("\nGenerating .env file")
            self.llm_service.generate_dot_env(api_definition)
        except Exception as e:
            self._log_error("Error creating .env file", e)
            raise

    def _verb_path_matches_root_path(self, verb_full_path: str, root_path: str):
        processed_verb_path = None

        if verb_full_path.startswith("{{"):
            processed_verb_path = verb_full_path.split("}}/")[1]
        elif verb_full_path.startswith("https://") or verb_full_path.startswith(
            "http://"
        ):
            match = re.search(r"\.[a-z]+/(.+)", verb_full_path)
            if match:
                processed_verb_path = match.group(1).lstrip("/")

        if processed_verb_path == root_path or processed_verb_path.startswith(
            root_path + "/"
        ):
            return True
        else:
            return False

    def generate(
        self,
        merged_api_definition_list: List[Dict[str, Any]],
        generate_tests: GenerationOptions,
    ):
        """Process the API definitions and generate models and tests"""
        try:
            self.logger.info("\nProcessing API definitions")

            if self.config.source == DataSource.POSTMAN:

                all_generated_models_info = []

                verb_chunks = merged_api_definition_list

                all_distinct_paths_no_query_params = (
                    self.postman_processor.get_all_distinct_paths_no_query_params(
                        verb_chunks
                    )
                )

                paths_grouped_by_service = self.llm_service.group_paths_by_service(
                    all_distinct_paths_no_query_params
                )

                service_chunks = self.postman_processor.map_verb_path_pairs_to_services(
                    verb_chunks, paths_grouped_by_service
                )

                verb_chunks_tagged_with_service = (
                    self.postman_processor.add_service_name_to_verb_chunks(
                        verb_chunks, paths_grouped_by_service
                    )
                )

                for service in service_chunks.items():

                    models = self._generate_models(service)

                    service_summary = self._generate_api_definition_summary(service)

                    all_generated_models_info.append(
                        {
                            "service": service[0],
                            "summary": service_summary,
                            "files": [model["path"] for model in models],
                            "models": models,
                        }
                    )

                for verb in verb_chunks_tagged_with_service:

                    generated_tests_and_responses = self._generate_tests(
                        verb,
                        all_generated_models_info,
                        GenerationOptions.MODELS_AND_FIRST_TEST,
                    )

                    updated_models_info = copy.deepcopy(all_generated_models_info)

                    for file in generated_tests_and_responses:

                        if "/responses" in file["path"]:

                            for models_on_path in all_generated_models_info:

                                if verb["service"] == models_on_path["service"]:

                                    model_on_path_copy = copy.deepcopy(models_on_path)
                                    model_on_path_copy["files"].append(file["path"])
                                    model_on_path_copy["models"].append(
                                        file["fileContent"]
                                    )
                                    updated_models_info.append(model_on_path_copy)

                                else:
                                    updated_models_info.append(models_on_path)

            else:
                models = None
                all_generated_models_info = []
                path_chunks = [
                    path
                    for path in merged_api_definition_list
                    if path["type"] == "path"
                ]
                verb_chunks = [
                    verb
                    for verb in merged_api_definition_list
                    if verb["type"] == "verb"
                ]

                for path in path_chunks:
                    if not self._should_process_endpoint(path["path"]):
                        continue

                    models = self._generate_models(path)
                    api_definition_summary = self._generate_api_definition_summary(path)

                    all_generated_models_info.append(
                        {
                            "path": path["path"],
                            "summary": api_definition_summary,
                            "files": [model["path"] for model in models],
                            "models": models,
                        }
                    )

                if generate_tests in (
                    GenerationOptions.MODELS_AND_FIRST_TEST,
                    GenerationOptions.MODELS_AND_TESTS,
                ):
                    for verb in verb_chunks:
                        self._generate_tests(
                            verb, all_generated_models_info, generate_tests
                        )

                self.logger.info(
                    f"\nGeneration complete. {self.models_count} models and {self.tests_count} tests were generated."
                )
        except Exception as e:
            self._log_error("Error processing definitions", e)
            raise

    def run_final_checks(self, generate_tests: GenerationOptions):
        """Run final checks like TypeScript compilation and tests"""
        try:
            result = self.command_service.run_typescript_compiler()
            success, _ = result

            if success and generate_tests in (
                GenerationOptions.MODELS_AND_FIRST_TEST,
                GenerationOptions.MODELS_AND_TESTS,
            ):
                self.command_service.run_tests()

            self.logger.info("Final checks completed")
        except Exception as e:
            self._log_error("Error during final checks", e)
            raise

    def _should_process_endpoint(self, path: str) -> bool:
        """Check if an endpoint should be processed based on configuration"""
        return self.config.endpoint is None or path.startswith(self.config.endpoint)

    def _generate_models(
        self, api_definition: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """Process a path definition and generate models"""
        try:
            # self.logger.info(f"\nGenerating models for path: {api_definition['path']}")
            models = []
            if self.config.source == DataSource.POSTMAN:
                models = self.llm_service.generate_models(api_definition)
            else:
                models = self.llm_service.generate_models(api_definition["yaml"])
            if models:
                self.models_count += len(models)
                self._run_code_quality_checks(models)
            return models
        except Exception as e:
            self._log_error(f"Error processing path definition for", e)
            raise

    def _generate_tests(
        self,
        verb_chunk: Dict[str, Any],
        models: List[Dict[str, Any]],
        generate_tests: GenerationOptions,
    ):
        """Generate tests for a specific verb (HTTP method) in the API definition"""
        try:

            models_copy = copy.deepcopy(models)

            if self.config.source == DataSource.POSTMAN:
                models_matched_by_path = None
                all_available_models_minus_models_matched_by_path = []

                for model in models_copy:

                    if verb_chunk["service"] == model["service"]:
                        models_matched_by_path = model["models"]

                    else:
                        all_available_models_minus_models_matched_by_path.append(
                            {
                                "summary": model["summary"],
                                "files": model["files"],
                            }
                        )

                read_files = self.llm_service.read_additional_model_info(
                    all_available_models_minus_models_matched_by_path,
                    models_matched_by_path,
                    verb_chunk,
                )

                tests = self.llm_service.generate_first_test(
                    read_files, verb_chunk, models_matched_by_path
                )

                if tests:
                    self.tests_count += 1
                    self._run_code_quality_checks(tests)

                return tests

            else:
                models_matched_by_path = None
                all_available_models_minus_models_matched_by_path = []

                for model in models_copy:
                    if self._verb_path_matches_root_path(
                        verb_chunk["path"], model["path"]
                    ):
                        models_matched_by_path = model["models"]
                    else:
                        all_available_models_minus_models_matched_by_path.append(
                            {
                                "path": model["path"],
                                "summary": model["summary"],
                                "files": model["files"],
                            }
                        )

                read_files = self.llm_service.read_additional_model_info(
                    all_available_models_minus_models_matched_by_path,
                    models_matched_by_path,
                    verb_chunk,
                )

                self.logger.info(
                    f"\nGenerating first test for path: {verb_chunk['path']} and verb: {verb_chunk['verb']}"
                )

                tests = self.llm_service.generate_first_test(
                    read_files, verb_chunk["yaml"], models_matched_by_path
                )

                if tests:
                    self.tests_count += 1
                    self._run_code_quality_checks(tests)
                    if generate_tests == GenerationOptions.MODELS_AND_TESTS:
                        additional_tests = self._generate_additional_tests(
                            tests, models, verb_chunk
                        )
                        tests = tests + additional_tests

                return tests

        except Exception as e:
            self._log_error(
                f"Error processing verb definition for {verb_chunk['path']} - {verb_chunk['verb']}",
                e,
            )
            raise

    def _generate_additional_tests(
        self,
        tests: List[Dict[str, Any]],
        models: List[Dict[str, Any]],
        api_definition: Dict[str, Any],
    ):
        """Generate additional tests based on the initial test and models"""
        try:
            self.logger.info(
                f"\nGenerating additional tests for path: {api_definition['path']} and verb: {api_definition['verb']}"
            )
            additional_tests = self.llm_service.generate_additional_tests(
                tests, models, api_definition["yaml"]
            )
            if additional_tests:
                self._run_code_quality_checks(additional_tests)

            return additional_tests

        except Exception as e:
            self._log_error(
                f"Error generating additional tests for {api_definition['path']} - {api_definition['verb']}",
                e,
            )
            raise

    def _run_code_quality_checks(self, files: List[Dict[str, Any]]):
        """Run code quality checks including TypeScript compilation, linting, and formatting"""
        try:

            def typescript_fix_wrapper(problematic_files, messages):
                self.llm_service.fix_typescript(problematic_files, messages)

            self.command_service.run_command_with_fix(
                self.command_service.run_typescript_compiler_for_files,
                typescript_fix_wrapper,
                files,
            )
            self.command_service.format_files()
            self.command_service.run_linter()
        except Exception as e:
            self._log_error("Error during code quality checks", e)
            raise

    def _generate_api_definition_summary(self, api_definition: Dict[str, Any]):
        """Generate a summary of a verb/path chunk"""
        try:
            return self.llm_service.generate_chunk_summary(api_definition)
        except Exception as e:
            self._log_error("Error during summary generation", e)
            raise
