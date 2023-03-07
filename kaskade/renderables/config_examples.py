from rich.markdown import Markdown

config_example_md = """
## Kafka

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

## Schema Registry

Simple connection example:

```yaml
schema.registry:
  url: http://localhost:8081
```

## Kaskade

Next settings are optional:

```yaml
kaskade:
  debug: off # enable debug mode, default off
  show.internals: off # show internal topics, default off
```

> `debug` enabled will generate logs into a specific log file, execute `kaskade --info` to get the log path.

## Other Examples

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
  basic.auth.user.info: ${SR_API_KEY}:${SR_API_SECRET}
```
"""


class ConfigExamples:
    def __rich__(self) -> Markdown:
        return Markdown(config_example_md)
