import sys
from logging import DEBUG
from pathlib import Path

from confluent_kafka import KafkaException
from rich.console import Console
from rich.markdown import Markdown

from kaskade import logger
from kaskade.config import Config
from kaskade.emojis import THINKING_FACE
from kaskade.renderables.config_examples import ConfigExamples
from kaskade.renderables.kaskade_info import KaskadeInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.kaskade_version import KaskadeVersion
from kaskade.tui import Tui


class Cli:
    def __init__(
        self,
        print_version: bool,
        print_information: bool,
        print_configs: bool,
        save_yml_file: bool,
        config_file: str,
    ) -> None:
        self.print_version = print_version
        self.print_information = print_information
        self.print_configs = print_configs
        self.save_yml_file = save_yml_file
        self.config_file = config_file

    def run(self) -> None:
        try:
            self.print_version_option()
            self.print_information_option()
            self.print_configs_option()
            self.save_yml_file_option()
            self.run_tui()
        except Exception as ex:
            message = str(ex)

            if isinstance(ex, KafkaException):
                message = ex.args[0].str()

            console = Console()
            console.print(
                '{} [bold red]A problem has occurred[/] [bold green]"{}"[/]'.format(
                    THINKING_FACE, message
                )
            )
            logger.critical("Error starting the app: %s", message)
            logger.exception(ex)

            sys.exit(1)

    def print_information_option(self) -> None:
        if not self.print_information:
            return

        console = Console()
        console.print(KaskadeInfo())

        sys.exit(0)

    def print_configs_option(self) -> None:
        if not self.print_configs:
            return

        console = Console()
        console.print(ConfigExamples())

        sys.exit(0)

    def print_version_option(self) -> None:
        if not self.print_version:
            return

        console = Console()
        console.print(KaskadeName())
        console.print(KaskadeVersion())

        sys.exit(0)

    def save_yml_file_option(self) -> None:
        if not self.save_yml_file:
            return

        yml_file = """kafka:
  bootstrap.servers: ${BOOTSTRAP_SERVERS}
  security.protocol: SASL_SSL
  sasl.mechanism: PLAIN
  sasl.username: ${CLUSTER_API_KEY}
  sasl.password: ${CLUSTER_API_SECRET}

schema.registry:
  url: ${SCHEMA_REGISTRY_URL}
  basic.auth.credentials.source: USER_INFO
  basic.auth.user.info: ${SR_API_KEY}:${SR_API_SECRET}
"""

        md_file = f"""```yaml
{yml_file}```"""

        path = Path(self.config_file)

        file = open(path, "w")
        file.write(yml_file)
        file.close()

        console = Console()
        console.print(Markdown(md_file, code_theme="ansi_dark"))
        console.print(f"File generated at {path.absolute()}")

        sys.exit(0)

    def run_tui(self) -> None:
        config = Config(self.config_file)
        is_debug = bool(config.kaskade.get("debug"))

        if is_debug:
            logger.setLevel(DEBUG)
            logger.debug("Starting in debug mode")

        logger.debug("Starting TUI")
        Tui.run(config=config)
