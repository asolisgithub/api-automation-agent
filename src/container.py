from src.configuration.cli import CLIArgumentParser
from src.framework_generator import FrameworkGenerator
from src.services.command_service import CommandService
from src.services.llm_service import LLMService
from src.services.file_service import FileService

from dependency_injector import containers, providers


class Container(containers.DeclarativeContainer):
    """Main container for the API framework generation process."""

    # Adapters
    config_adapter = providers.DependenciesContainer()
    processors_adapter = providers.DependenciesContainer()

    config = providers.Singleton(config_adapter.config)

    # CLI components
    cli_parser = providers.Factory(CLIArgumentParser)

    # Processors
    swagger_processor = processors_adapter.swagger_processor
    postman_processor = processors_adapter.postman_processor

    # Services
    file_service = providers.Factory(FileService)
    llm_service = providers.Factory(
        LLMService,
        config=config,
        file_service=file_service,
    )
    command_service = providers.Factory(
        CommandService,
        config=config,
    )

    # Framework generator
    framework_generator = providers.Factory(
        FrameworkGenerator,
        config=config,
        llm_service=llm_service,
        command_service=command_service,
        file_service=file_service,
        swagger_processor=swagger_processor,
        postman_processor=postman_processor,
    )
