import shlex
import subprocess
import sys

from rich.console import Console

from kaskade.styles.unicodes import DOWN_TRIANGLE


class CommandProcessor:
    def __init__(self, commands):
        self.commands = commands

    def run(self):
        console = Console()

        for name, command in self.commands.items():
            console.print()
            console.rule(f"{DOWN_TRIANGLE} [bold blue]{name.lower()}", align="left")
            console.print(f"[bold yellow]{command}[/]")
            command_split = shlex.split(command)
            result = subprocess.run(command_split)
            if result.returncode:
                console.print(
                    f"\n[bold red]Error:exclamation:[/] in [bold blue]{name} ([bold yellow]{command}[/])[/]"
                )
                sys.exit(result.returncode)


if __name__ == "__main__":
    test_commands = {"list files": "ls .", "testing echo": "echo 'hello world'"}
    command_processor = CommandProcessor(test_commands)
    command_processor.run()
