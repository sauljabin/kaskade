from rich.columns import Columns
from rich.console import Group
from rich.markdown import Markdown

md_doc = """
```yaml
kafka:
  bootstrap.servers: localhost:9092
```

ssl encryption example

```yaml
kafka:
  bootstrap.servers: localhost:9092
  security.protocol: SSL
```

env variables support

```yaml
kafka:
  bootstrap.servers: ${BOOTSTRAP_SERVERS}
```

enable debug mode (default `off`)

```yaml
kaskade:
  debug: on
```

disable auto-refresh (default `on`)

```yaml
kaskade:
  refresh: off
```

changing the refresh rate (default `5` secs)

```yaml
kaskade:
  refresh-rate: 5
"""


class ConfigExamples:
    def __rich__(self) -> Group:
        return Group(
            "[magenta bold]configurations:[/]", Columns([Markdown(md_doc)], width=55)
        )
