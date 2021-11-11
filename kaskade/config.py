import os
import re
from pathlib import Path

import yaml

from kaskade import logger


class Config:
    def __init__(self, path: str) -> None:
        self.path: str = "" if path is None else path

        config_files = ["kaskade.yml", "kaskade.yaml", "config.yml", "config.yaml"]

        if len(self.path) > 0:
            if not Path(self.path).exists():
                raise Exception(f"Config file {path} not found")
        else:
            default_config_file = next(
                iter([path for path in config_files if Path(path).exists()]), None
            )
            if default_config_file is None:
                raise Exception(
                    "Default config file kaskade.yml, kaskade.yaml, "
                    "config.yml or config.yaml not found"
                )

            self.path = default_config_file

        with open(self.path, "r") as file:
            self.text: str = file.read()

        pattern = re.compile(r"\${(.*)}")

        for file_variable in re.findall(pattern, self.text):
            system_variable = os.environ.get(file_variable)
            if system_variable is None:
                raise Exception(
                    f"Environment variable ${file_variable} not found in the system"
                )
            self.text = self.text.replace(f"${{{file_variable}}}", system_variable)

        self.yaml = yaml.safe_load(self.text)
        self.kafka = self.yaml.get("kafka")
        self.kaskade = self.yaml.get("kaskade")
        self.schema_registry = self.yaml.get("schema-registry")
        self.kafka["logger"] = logger
