import configparser
from pathlib import Path


class _CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr: str) -> str:
        return optionstr


def file_to_bytes(file_path: str) -> bytes:
    return Path(file_path).expanduser().read_bytes()


def load_ini(file_path: str) -> dict[str, dict[str, str]]:
    parser = _CaseSensitiveConfigParser(interpolation=None, delimiters=("=",))

    try:
        parser.read_string(Path(file_path).expanduser().read_text())
    except configparser.Error as ex:
        raise ValueError(f"Invalid INI: {ex}") from ex

    return {section: dict(parser.items(section, raw=True)) for section in parser.sections()}
