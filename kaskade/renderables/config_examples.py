from rich.columns import Columns
from rich.console import Group
from rich.markdown import Markdown

md_doc = """
### Kafka

Simple connection example:

```yaml
kafka:
  bootstrap.servers: localhost:9092
```

SSL encryption example:

```yaml
kafka:
  bootstrap.servers: localhost:9092
  security.protocol: SSL
```

> For more information about SSL encryption and SSL authentication go to
> [confluent-kafka](https://github.com/confluentinc/confluent-kafka-python#ssl-certificates) and
> [librdkafka](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client).

Support for env variables:

```yaml
kafka:
  bootstrap.servers: ${BOOTSTRAP_SERVERS}
```

### Schema Registry

Simple connection example:

```yaml
schema.registry:
  url: http://localhost:8081
```

### Kaskade

Next settings are optional:

```yaml
kaskade:
  debug: off # enable debug mode, default off
  refresh: on # enable auto-refresh, default on
  refresh-rate: 5 # auto-refresh rate, default 5 secs
```

> `debug` enabled will generate logs into a specific log file, execute `kaskade --info` to get the log path.

### Other Examples

Confluent Cloud:

```yaml
kafka:
  bootstrap.servers: ${BOOTSTRAP_SERVERS}
  security.protocol: SASL_SSL
  sasl.mechanism: PLAIN
  sasl.username: ${CLUSTER_API_KEY}
  sasl.password: ${CLUSTER_API_SECRET}

schema.registry:
  url: ${SCHEMA_REGISTRY_URL}
  basic.auth.credentials.source: USER_INFO
  basic.auth.user.info: ${SR_API_KEY}:${SR_API_SECRET}
```
"""


class ConfigExamples:
    def __rich__(self) -> Group:
        return Group(Columns([Markdown(md_doc, code_theme="ansi_dark")], width=100))
