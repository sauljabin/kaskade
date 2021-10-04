import subprocess
import sys

from rich.console import Console

from kaskade.unicodes import DOWN_TRIANGLE


class CommandProcessor:
    def __init__(self, commands):
        self.commands = commands

    def run(self):
        console = Console()

        for name, command in self.commands.items():
            console.rule(f"{DOWN_TRIANGLE} [bold blue]{name.lower()}", align="left")
            console.print(f"  [bold yellow]{command}[/]")
            result = subprocess.run(command.split())
            if result.returncode:
                console.print(
                    f":rotating_light: [bold red]Error executing:[/] [bold yellow]{command}[/]"
                )
                sys.exit(result.returncode)


if __name__ == "__main__":
    command_processor = CommandProcessor({"list files": "ls ."})
    command_processor.run()
