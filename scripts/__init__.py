import shlex
import subprocess
import sys

from rich.console import Console


class CommandProcessor:
    def __init__(self, commands: dict[str, str], rollback: dict[str, str] | None = None) -> None:
        if rollback is None:
            rollback = {}
        self.commands = commands
        self.rollback = rollback
        self.console = Console()

    def run(self) -> str:
        output = ""
        for name, command in self.commands.items():
            result = self.execute_command(name, command)
            if result.returncode:
                self.console.print(
                    "\n[bold red]Error[/] when executing "
                    f'[bold blue]"{name}" ([bold yellow]{command}[/])[/]:exclamation::\n'
                    f"[red]{result.stdout}{result.stderr}[/]\n"
                )

                if self.rollback:
                    self.console.print("[bold yellow]Rolling back:[/]")
                    for rollback_name, rollback_command in self.rollback.items():
                        self.execute_command(rollback_name, rollback_command)

                sys.exit(result.returncode)
            else:
                output += result.stdout

        return output

    def execute_command(self, name: str, command: str) -> subprocess.CompletedProcess:
        self.console.print()
        self.console.print(f"[bold blue]{name.lower()}:")
        self.console.print(f"[bold yellow]{command}[/]")
        return subprocess.run(shlex.split(command), capture_output=True, text=True)


if __name__ == "__main__":
    test_commands = {
        "list files": "ls .",
        "testing echo": "echo 'hello world'",
    }
    test_rollback = {"echo rollback": "echo 'error'"}
    command_processor = CommandProcessor(test_commands, test_rollback)
    command_processor.run()
