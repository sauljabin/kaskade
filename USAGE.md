# Usage

This guide provides common Kaskade commands for connecting to Kafka, consuming records, and configuring Schema Registry, TLS, and cloud services.

## Configuration examples

### Multiple bootstrap servers

```bash
kaskade admin -b my-kafka:9092,my-kafka:9093
```

### Consume and deserialize

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic -k json -v json
```

Supported deserializers: `bytes`, `boolean`, `string`, `long`, `integer`, `double`, `float`, `json`, `avro`, `protobuf`, and `registry`.

### Themes

Kaskade defaults to the `eva01` Unit-01-inspired theme. Choose any Textual theme at launch:

```bash
kaskade admin -b my-kafka:9092 --theme dracula
```

While Kaskade is running, press `:` (or `Ctrl+P`) and select a theme from the Commands window. Theme changes apply only to the current session.

### Admin auto-refresh

Admin mode refreshes topic metadata and metrics every 30 seconds. Auto-refresh pauses while a dialog, topic details, Help, or the command palette is open, then refreshes after returning to the topic list. Press `Ctrl+R` to refresh immediately.

Configure the interval in Kaskade's `config.yaml`:

```yaml
admin:
  refresh_interval_seconds: 30
```

Use `0` to disable auto-refresh. Enabled intervals must be at least 5 seconds. Missing or invalid values use the 30-second default and invalid values produce an in-app warning.

### Keyboard shortcuts

Kaskade supports arrow keys and Vim-style navigation. The defaults follow familiar k9s conventions where the applications have equivalent actions.

| Action | Shortcut |
| --- | --- |
| Move | `h`, `j`, `k`, `l` or arrow keys |
| First or last item | `g` or `G` |
| Page up or down | `PageUp` or `PageDown` |
| Select or apply a modal action | `Enter` |
| Back or clear a filter | `Esc` |
| Help | `?` or `F1` |
| Commands | `:` or `Ctrl+P` |
| Quit | `Ctrl+C` |
| Filter | `/` or `Ctrl+F` |
| Describe a topic | `d` or `Enter` |
| Create a topic | `n` or `Ctrl+N` |
| Edit a topic | `e` or `Ctrl+E` |
| Delete a topic | `Ctrl+D` |
| Refresh topics | `Ctrl+R` |
| Consume more records | `n` |
| Change record chunk size | `#` |

Help opens in a contextual window above the current screen. Navigate it with `j`/`k`, arrows, Page Up/Down, or `g`/`G`, then close it with `Esc`, `q`, `?`, or `F1`.

Plain-character application shortcuts do not intercept typing in filter and editor fields.

#### Custom keymap

On Linux and macOS, Kaskade reads `$XDG_CONFIG_HOME/kaskade/config.yaml`. If `XDG_CONFIG_HOME` is not set, it reads `~/.config/kaskade/config.yaml`. Set `KASKADE_CONFIG` to use a different file.

Copy the complete example to the default location before customizing it:

```bash
mkdir -p ~/.config/kaskade
cp examples/config.yaml ~/.config/kaskade/config.yaml
```

The `keymap` values use Textual key names. Separate keys with commas to assign aliases:

```yaml
keymap:
  app.quit: ctrl+c
  help.toggle: question_mark,f1
  kaskade.navigation.down: down,j
  kaskade.navigation.up: up,k
  kaskade.topics.filter: slash
  kaskade.topics.delete: D
```

Common configurable binding IDs are:

| Context | Binding IDs |
| --- | --- |
| Application | `app.quit`, `app.command-palette`, `help.toggle`, `kaskade.help.close` |
| Navigation | `kaskade.navigation.up`, `.down`, `.left`, `.right`, `.first`, `.last`, `.page-up`, `.page-down`, `.select` |
| Topics | `kaskade.topics.describe`, `.filter`, `.refresh`, `.create`, `.edit`, `.delete`, `.show-all` |
| Records | `kaskade.records.show`, `.consume`, `.filter`, `.chunk-size`, `.show-all` |
| Dialogs | `kaskade.filter-topics.apply`, `kaskade.delete-topic.confirm`, `kaskade.filter-records.apply`, `kaskade.chunk-size.select` |
| Editors | `kaskade.create-topic.save`, `kaskade.edit-topic.save` |

Unknown binding IDs, invalid key names, and malformed configuration produce an in-app warning while Kaskade continues with its default bindings.

### Consume from the beginning

```bash
kaskade consumer -b my-kafka:9092 -t my-topic --from-beginning
```

### Schema Registry

Connect to a Schema Registry:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry url=http://my-schema-registry:8081
```

See the [Confluent Schema Registry client documentation](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html#schemaregistry-client) for additional Schema Registry settings.

### Apicurio Registry

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry url=http://my-apicurio-registry:8081/apis/ccompat/v7
```

Learn more at [Apicurio Registry](https://github.com/apicurio/apicurio-registry).

### SSL encryption

```bash
kaskade admin -b my-kafka:9092 -c security.protocol=SSL
```

See [Configure librdkafka client](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client) for SSL encryption and authentication settings.

### Kafka client properties file

Both admin and consumer modes accept Kafka client properties from a separate file:

```bash
kaskade admin \
    -b my-kafka:9092 \
    --config-file kafka.properties

kaskade consumer \
    -b my-kafka:9092 \
    -t my-topic \
    --config-file kafka.properties
```

The file uses one `property=value` entry per line. Blank lines and lines beginning with `#` are ignored. See [examples/kafka.properties](examples/kafka.properties) for a SASL/SSL example:

```properties
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.username=replace-with-your-api-key
sasl.password=replace-with-your-api-secret
client.id=kaskade
```

This file contains only properties for `confluent-kafka`; Kaskade UI, admin, and keymap settings remain in `config.yaml` as documented above. The required `-b/--bootstrap-servers` option sets `bootstrap.servers`, so it does not need to appear in `kafka.properties`.

Configuration precedence, from lowest to highest, is:

1. Properties loaded from `--config-file`.
2. Repeated `-c/--config property=value` options.
3. `-b/--bootstrap-servers` for `bootstrap.servers`.
4. In consumer mode, `--from-beginning` for `auto.offset.reset=earliest`.

### Confluent Cloud

Admin:

```bash
kaskade admin -b ${BOOTSTRAP_SERVERS} \
        -c security.protocol=SASL_SSL \
        -c sasl.mechanism=PLAIN \
        -c sasl.username=${CLUSTER_API_KEY} \
        -c sasl.password=${CLUSTER_API_SECRET}
```

Consumer:

```bash
kaskade consumer -b ${BOOTSTRAP_SERVERS} -t my-avro-topic \
        -k string -v registry \
        -c security.protocol=SASL_SSL \
        -c sasl.mechanism=PLAIN \
        -c sasl.username=${CLUSTER_API_KEY} \
        -c sasl.password=${CLUSTER_API_SECRET} \
        --registry url=${SCHEMA_REGISTRY_URL} \
        --registry basic.auth.user.info=${SR_API_KEY}:${SR_API_SECRET}
```

See the [Kafka client quick start for Confluent Cloud](https://docs.confluent.io/cloud/current/client-apps/config-client.html).

### Docker

Admin:

```bash
docker run --rm -it --network my-network sauljabin/kaskade:latest \
    admin -b my-kafka:9092
```

Consumer:

```bash
docker run --rm -it --network my-network sauljabin/kaskade:latest \
    consumer -b my-kafka:9092 -t my-topic
```

### Avro consumer

Consume using a `my-schema.avsc` schema file:

```bash
kaskade consumer -b my-kafka:9092 --from-beginning \
        -k string -v avro \
        -t my-avro-topic \
        --avro value=my-schema.avsc
```

### Protobuf consumer

Install `protoc`:

```bash
brew install protobuf
```

Generate a descriptor set from a `.proto` file:

```bash
protoc --include_imports \
       --descriptor_set_out=my-descriptor.desc \
       --proto_path=${PROTO_PATH} \
       ${PROTO_PATH}/my-proto.proto
```

Consume using `my-descriptor.desc`:

```bash
kaskade consumer -b my-kafka:9092 --from-beginning \
        -k string -v protobuf \
        -t my-protobuf-topic \
        --protobuf descriptor=my-descriptor.desc \
        --protobuf value=mypackage.MyMessage
```

See the [Protocol Buffers documentation](https://protobuf.dev/programming-guides/techniques/#self-description) for more about `FileDescriptorSet`.
