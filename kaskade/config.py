from pathlib import Path

import yaml


class Config:
    def __init__(self, path):
        self.path = path
        config_files = ["kaskade.yml", "kaskade.yaml", "config.yml", "config.yaml"]
        if self.path:
            if not Path(self.path).exists():
                raise Exception(f"Config file {path} not found")
        else:
            default_config_file = next(
                iter([path for path in config_files if Path(path).exists()]), None
            )
            self.path = default_config_file
            if not self.path:
                raise Exception(
                    "Default config file kaskade.yml, kaskade.yaml, "
                    "config.yml or config.yaml not found"
                )

        with open(self.path, "r") as file:
            self.text = file.read()
            self.yaml = yaml.safe_load(self.text)
            self.kafka = self.yaml.get("kafka")
            self.kaskade = self.yaml.get("kaskade")
