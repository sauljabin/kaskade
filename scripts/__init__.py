import shlex
import subprocess
import sys

from rich.console import Console


class CommandProcessor:
    def __init__(self, commands, rollback={}):
        self.commands = commands
        self.rollback = rollback
        self.console = Console()

    def run(self):
        for name, command in self.commands.items():
            result = self.execute_command(name, command)
            if result.returncode:
                self.console.print(
                    "\n[bold red]Error:exclamation:[/] when executing "
                    f'[bold blue]"{name}" ([bold yellow]{command}[/])[/]:\n'
                    f"[red]{result.stdout.decode().strip()}[/]\n"
                    "Rolling back."
                )
                for rollback_name, rollback_command in self.rollback.items():
                    self.execute_command(rollback_name, rollback_command)

                sys.exit(result.returncode)

    def execute_command(self, name, command):
        self.console.print()
        self.console.print(f"[bold blue]{name.lower()}:")
        self.console.print(f"[bold yellow]{command}[/]")
        return subprocess.run(shlex.split(command), capture_output=True)


if __name__ == "__main__":
    test_commands = {
        "list files": "ls .",
        "testing echo": "echo 'hello world'",
        "no command": "false",
    }
    test_rollback = {"echo rollback": "echo 'error'"}
    command_processor = CommandProcessor(test_commands, test_rollback)
    command_processor.run()
