# Usage

This guide provides common Kaskade commands for connecting to Kafka, consuming
records, and configuring Schema Registry, TLS, and cloud services.

## Common commands

### Multiple bootstrap servers

```bash
kaskade admin -b my-kafka:9092,my-kafka:9093
```

### Consume and deserialize

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic -k json -v json
```

Supported deserializers are `bytes`, `boolean`, `string`, `long`, `integer`,
`double`, `float`, `json`, `avro`, `protobuf`, and `registry`.

Deserializer-specific settings use repeatable `property=value` options. Use
`--bytes` for byte presentation, `--json` for local JSON framing, `--avro` for
local Avro schemas and framing, `--protobuf` for descriptors, message names,
and framing, and `--registry` for Schema Registry client properties. Repeat the
relevant option once per property. See the [Schema Registry](#schema-registry)
and [format-specific consumer](#format-specific-consumers) examples below.

## Application settings and controls

### Themes

Kaskade defaults to the `eva01` Unit-01-inspired theme. Choose any Textual theme
at launch:

```bash
kaskade admin -b my-kafka:9092 --theme dracula
```

While Kaskade is running, press `:` (or `Ctrl+P`) and select a theme from the
Commands window. Theme changes apply only to the current session.

### Admin auto-refresh

Admin mode refreshes topic metadata and metrics every 30 seconds. Auto-refresh
pauses while a dialog, topic details, Help, or the command palette is open, then
refreshes after returning to the topic list. Press `Ctrl+R` to refresh
immediately.

Configure the interval in Kaskade's `config.yaml`:

```yaml
admin:
  refresh_interval_seconds: 30
```

Use `0` to disable auto-refresh. Enabled intervals must be at least 5 seconds.
Missing or invalid values use the 30-second default; invalid values also
produce an in-app warning.

Override the configured interval for one admin session with `--refresh-interval`:

```bash
kaskade admin -b my-kafka:9092 --refresh-interval 10
kaskade admin -b my-kafka:9092 --refresh-interval 0
```

The command-line value takes precedence over `config.yaml` and follows the same
validation rules.

### Keyboard shortcuts

Kaskade supports arrow keys and Vim-style navigation. The defaults follow
familiar k9s conventions where the applications have equivalent actions.

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
| Copy selected topic or record | `y` |
| Copy selected screen text | `Cmd+C` on macOS or `Ctrl+Shift+C` on Linux |
| Export selected record | `Ctrl+E` |
| Consume more records | `n` |
| Change record chunk size | `#` |

Help opens in a contextual window above the current screen and lists every
effective shortcut alias. Navigate it with `j`/`k`, arrows, Page Up/Down, or
`g`/`G`, then close it with `Esc`, `q`, `?`, or `F1`. The command palette
includes this contextual Help window instead of Textual's generic Keys panel.

Plain-character application shortcuts do not intercept typing in filter and
editor fields.

#### Custom keymap

On Linux and macOS, Kaskade reads `$XDG_CONFIG_HOME/kaskade/config.yaml`. If
`XDG_CONFIG_HOME` is not set, it reads `~/.config/kaskade/config.yaml`. Set
`KASKADE_CONFIG` to use a different file.

Copy the complete example to the default location before customizing it:

```bash
mkdir -p ~/.config/kaskade
cp examples/config.yaml ~/.config/kaskade/config.yaml
```

The `keymap` values use Textual key names. Separate keys with commas to assign
aliases:

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
| Topics | `kaskade.topics.describe`, `.copy`, `.filter`, `.refresh`, `.create`, `.edit`, `.delete`, `.show-all` |
| Records | `kaskade.records.show`, `.copy`, `.export`, `.consume`, `.filter`, `.chunk-size`, `.show-all` |
| Dialogs | `kaskade.filter-topics.apply`, `kaskade.delete-topic.confirm`, `kaskade.filter-records.apply`, `kaskade.chunk-size.select` |
| Editors | `kaskade.create-topic.save`, `kaskade.edit-topic.save` |

Unknown binding IDs, invalid key names, and malformed configuration produce an
in-app warning while Kaskade continues with its default bindings.

### Copy topics and consumed records

Select a topic in Admin mode or a consumed record in Consumer mode, then press
`y` to copy the topic name or readable record JSON. Copy is also available in
Topic Details, Record Details, contextual Help, and Commands, but is omitted
from the Footer.

Selecting screen text is separate: use `Cmd+C` on macOS or `Ctrl+Shift+C` on
Linux. `Ctrl+C` always quits Kaskade, even while text is selected.

#### OSC 52 compatibility

Kaskade uses [Textual's terminal clipboard API](https://textual.textualize.io/api/app/#textual.app.App.copy_to_clipboard),
which sends an [OSC 52](https://github.com/tmux/tmux/wiki/Clipboard) request to
the terminal emulator. Kaskade cannot detect whether the terminal accepted it,
so a confirmation toast means the request was sent, not that the system
clipboard was verified.

| Terminal | Compatibility |
| --- | --- |
| [iTerm2](https://iterm2.com/documentation-preferences-general.html) | Supported after enabling **Applications in terminal may access clipboard** |
| [Kitty](https://sw.kovidgoyal.net/kitty/conf/#opt-kitty.clipboard_control) | Supported; clipboard writes are enabled by default |
| [WezTerm](https://wezterm.org/escape-sequences.html#operating-system-command-sequences) | Supported |
| [Alacritty](https://alacritty.org/config-alacritty.html) | Supported; `terminal.osc52` defaults to `OnlyCopy` |
| [Ghostty](https://ghostty.org/docs/config/reference#clipboard-write) | Supported; clipboard writes are enabled by default |
| [VS Code integrated terminal](https://code.visualstudio.com/updates/v1_91#_support-for-copy-and-paste-escape-sequence-osc-52) | Supported in VS Code 1.91 or later |
| [Warp](https://github.com/warpdotdev/warp/issues/10516) | Conditionally supported; verify the installed version because of an active OSC 52 regression on macOS |
| xterm | Supported when OSC 52 is explicitly enabled |
| Apple Terminal.app | Not supported |
| VTE-based terminals: GNOME Terminal (Ubuntu's built-in terminal), GNOME Console/Ptyxis, Terminator, and XFCE Terminal | Not supported |

OSC 52 writes to the clipboard owned by the terminal emulator on the user's
computer. It can therefore work when Kaskade runs through SSH or
`kubectl exec -it`; the remote machine or pod does not need its own clipboard.
Every intermediate layer must preserve the escape sequence. Terminal
multiplexers such as tmux may require
[additional clipboard configuration](https://github.com/tmux/tmux/wiki/Clipboard#quick-summary),
and browser terminals or other relays may filter OSC 52.

### Export a consumed record

Select a record in consumer mode or open its details, then press `Ctrl+E` to export it as
JSON. Kaskade saves the file to the same destination as the Screenshot command: the
Downloads directory in a local terminal or a browser download when web-hosted. The export
includes the topic, partition, offset, timestamp, headers, and the deserialized key and value with
their deserializer types. Export Record is omitted from the Footer; find it in contextual
Help or Commands.

Record details, clipboard copies, and exports share the same JSON structure. Primitive and
plain JSON deserializers omit Registry schema metadata:

```json
{
  "topic": "orders",
  "partition": 0,
  "offset": 42,
  "timestamp": "2026-08-28T14:12:05.120Z",
  "headers": [
    {"key": "source", "value": "storefront"}
  ],
  "key": {
    "content": "order-1048",
    "deserializer": {"type": "STRING"}
  },
  "value": {
    "content": {"status": "paid"},
    "deserializer": {"type": "JSON"}
  }
}
```

Schema Registry metadata is independent for the key and value. Kaskade includes it when
the schema ID resolves to an unambiguous subject and version:

```json
{
  "key": {
    "content": {"id": "order-1049"},
    "deserializer": {
      "type": "REGISTRY",
      "schema": {
        "id": 12,
        "subject": "orders-key",
        "version": 2,
        "type": "AVRO"
      }
    }
  },
  "value": {
    "content": {"status": "shipped"},
    "deserializer": {
      "type": "REGISTRY",
      "schema": {
        "id": 27,
        "subject": "orders-value",
        "version": 5,
        "type": "JSON"
      }
    }
  }
}
```

Headers remain an ordered array of `key` and `value` objects because Kafka permits repeated
header names. JSON timestamps use UTC ISO 8601 with millisecond precision, or `null` when
Kafka supplies no timestamp. Tombstone keys and values use `content: null`. Local Avro,
local Protobuf, and non-schema deserializers omit `schema`. A Registry deserializer also
omits `schema` when its metadata cannot be resolved unambiguously.
In the records table, absent keys and values appear as a colored `null`; hover the cell
to distinguish an absent key from a tombstone value.

Byte content stays directly in `content`, and its BYTES deserializer carries the
presentation format. Base64 is the default portable format:

```json
{
  "content": "SGVsbG8gd29ybGQ=",
  "deserializer": {
    "type": "BYTES",
    "format": "BASE64"
  }
}
```

Configure byte presentation globally or override it for one field:

```bash
--bytes format=base64 \
--bytes key.format=hex \
--bytes value.format=byte-array
```

Supported formats are `base64`, `hex`, `byte-array`, and `python`. Values are
case-insensitive, and underscores such as `BYTE_ARRAY` normalize to `byte-array`.
For a key or value, its scoped property overrides `format`; header fallbacks use
only the global format. The same resolved format applies to explicitly selected
BYTES fields and error BYTES deserializers. Null BYTES fields omit `format` because
they contain no bytes to interpret.

## Consumer behavior

### Choose the starting position

```bash
kaskade consumer -b my-kafka:9092 -t my-topic --earliest
```

`--earliest` consumes all topic partitions from their earliest currently available
offsets. To consume only selected partitions, repeat `--partition`:

```bash
kaskade consumer -b my-kafka:9092 -t my-topic \
        --partition 1:10 \
        --partition 2:earliest \
        --partition 3
```

The format is `partition[:offset|earliest]`. A numeric offset, including `0`, is an
absolute Kafka offset. `earliest` resolves to the partition's current low watermark, and
an omitted offset starts at the normal latest position. `--earliest` and `--partition`
cannot be combined.

### Deserialization failures

If a configured key or value deserializer cannot decode an individual record,
Kaskade shows `⚠`, displays that field using a BYTES error deserializer, and keeps
consuming. The recovered content uses the configured byte format, while the
diagnostic is nested inside the requested deserializer:

```json
{
  "content": "/w==",
  "deserializer": {
    "type": "REGISTRY",
    "error": {
      "message": "Unexpected magic byte -1",
      "deserializer": {
        "type": "BYTES",
        "format": "BASE64"
      }
    }
  }
}
```

Valid headers remain `{key, value}` objects. If a header is not valid UTF-8,
its raw value uses the global byte format and the header includes the same
nested error-deserializer metadata:

```json
{
  "key": "binary",
  "value": "/w==",
  "deserializer": {
    "type": "STRING",
    "error": {
      "message": "Invalid UTF-8 payload",
      "deserializer": {
        "type": "BYTES",
        "format": "BASE64"
      }
    }
  }
}
```

Record details, copy, and export preserve this structure. Hover the warning cell
to see the same diagnostic in a tooltip. The other field remains decoded normally.
Registry subject/version lookup is best-effort and cached; missing or ambiguous
metadata omits `schema` without turning successful content into an error fallback.

## Connections and security

### Schema Registry

Connect to a Schema Registry:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry url=http://my-schema-registry:8081
```

See the
[Confluent Schema Registry client documentation](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html#schemaregistry-client)
for additional Schema Registry settings.

#### Apicurio Registry

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

See
[Configure librdkafka client](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client)
for SSL encryption and authentication settings.

### Kafka client properties file

Both admin and consumer modes accept Kafka client properties from a separate
file:

```bash
kaskade admin \
    --config-file kafka.properties

kaskade consumer \
    -t my-topic \
    --config-file kafka.properties
```

The file uses one `property=value` entry per line. Blank lines and lines
beginning with `#` are ignored. See
[examples/kafka.properties](examples/kafka.properties) for a SASL/SSL example:

```properties
bootstrap.servers=my-kafka:9092
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.username=replace-with-your-api-key
sasl.password=replace-with-your-api-secret
client.id=kaskade
```

This file contains only properties for `confluent-kafka`; Kaskade UI, admin,
and keymap settings remain in `config.yaml` as documented above. Both commands
require a non-empty `bootstrap.servers` after Kafka properties are merged. It
can come from `--config-file`, an inline property, or the dedicated option:

```bash
kaskade admin --config bootstrap.servers=my-kafka:9092
kaskade consumer -t my-topic --config bootstrap.servers=my-kafka:9092
```

`-b/--bootstrap-servers` remains the most concise choice for ordinary commands
and overrides a value from Kafka client configuration. For example, this uses
`override-kafka:9092` while retaining the other file and inline properties:

```bash
kaskade admin \
    --config-file kafka.properties \
    --config client.id=temporary-kaskade \
    -b override-kafka:9092
```

Configuration precedence, from lowest to highest, is:

1. Properties loaded from `--config-file`.
2. Repeated `-c/--config property=value` options.
3. When supplied, `-b/--bootstrap-servers` for `bootstrap.servers`.
4. `--aws property=value` for the Amazon MSK IAM authentication properties.
5. In consumer mode, `--earliest` for `auto.offset.reset=earliest`.

### Amazon MSK with IAM authentication

Pass the AWS region to enable IAM authentication in either mode:

```bash
kaskade admin -b ${AWS_MSK_BOOTSTRAP_SERVERS} --aws region=us-east-1

kaskade consumer -b ${AWS_MSK_BOOTSTRAP_SERVERS} -t my-topic \
        --aws region=us-east-1
```

Kaskade configures `security.protocol=SASL_SSL`, `sasl.mechanism=OAUTHBEARER`,
and automatic token refresh. Credentials are discovered through the standard
AWS credential provider chain, so environment variables, shared AWS profiles
(including `AWS_PROFILE`), and IAM roles attached to AWS workloads are
supported without passing credentials to Kaskade.

See
[Configure clients for IAM access control](https://docs.aws.amazon.com/msk/latest/developerguide/configure-clients-for-iam-access-control.html)
for the Amazon MSK broker and IAM policy requirements.

#### IAM permissions

The IAM principal used by `--aws` needs these `kafka-cluster` actions:

| Mode | Required actions |
| --- | --- |
| Admin (read only) | `Connect`, `DescribeTopic`, `DescribeTopicDynamicConfiguration`, `DescribeGroup` |
| Admin (full access) | Read-only actions plus `CreateTopic`, `AlterTopic`, `DeleteTopic`, `AlterTopicDynamicConfiguration` |
| Consumer | `Connect`, `DescribeTopic`, `ReadData`, `DescribeGroup`, `AlterGroup` |
| Sandbox population | `Connect`, `CreateTopic`, `DescribeTopic`, `WriteData` |

This policy enables all admin and consumer features. Replace the placeholders
and narrow the topic wildcard when appropriate.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectToCluster",
      "Effect": "Allow",
      "Action": "kafka-cluster:Connect",
      "Resource": "arn:aws:kafka:<region>:<account-id>:cluster/<cluster-name>/<cluster-uuid>"
    },
    {
      "Sid": "ManageAndReadTopics",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:CreateTopic",
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:AlterTopic",
        "kafka-cluster:DeleteTopic",
        "kafka-cluster:DescribeTopicDynamicConfiguration",
        "kafka-cluster:AlterTopicDynamicConfiguration",
        "kafka-cluster:ReadData"
      ],
      "Resource": "arn:aws:kafka:<region>:<account-id>:topic/<cluster-name>/<cluster-uuid>/*"
    },
    {
      "Sid": "InspectConsumerGroups",
      "Effect": "Allow",
      "Action": "kafka-cluster:DescribeGroup",
      "Resource": "arn:aws:kafka:<region>:<account-id>:group/<cluster-name>/<cluster-uuid>/*"
    },
    {
      "Sid": "UseKaskadeConsumerGroups",
      "Effect": "Allow",
      "Action": "kafka-cluster:AlterGroup",
      "Resource": "arn:aws:kafka:<region>:<account-id>:group/<cluster-name>/<cluster-uuid>/kaskade-*"
    }
  ]
}
```

Consumer group access can be limited to `kaskade-*` because Kaskade creates
ephemeral groups named `kaskade-<uuid>`. For read-only admin access, remove
`CreateTopic`, `AlterTopic`, `DeleteTopic`, `AlterTopicDynamicConfiguration`,
and `ReadData` from the topic statement, then remove the
`UseKaskadeConsumerGroups` statement.

Use this policy for sandbox population:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectToCluster",
      "Effect": "Allow",
      "Action": "kafka-cluster:Connect",
      "Resource": "arn:aws:kafka:<region>:<account-id>:cluster/<cluster-name>/<cluster-uuid>"
    },
    {
      "Sid": "CreateAndPopulateTopics",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:CreateTopic",
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:WriteData"
      ],
      "Resource": "arn:aws:kafka:<region>:<account-id>:topic/<cluster-name>/<cluster-uuid>/*"
    }
  ]
}
```

See AWS's [authorization action semantics](https://docs.aws.amazon.com/msk/latest/developerguide/kafka-actions.html)
and [common client policy use cases](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control-use-cases.html)
for dependencies and resource formats.

### Kafka ACLs

For SASL/SCRAM and mTLS connections, grant the Kafka principal these operations:

| Mode | Topic ACLs | Group ACLs | Cluster ACLs |
| --- | --- | --- | --- |
| Admin (read only) | `Describe`, `DescribeConfigs` | `Describe` on groups to display | `Describe` |
| Admin (full access) | `Describe`, `DescribeConfigs`, `Create`, `Alter`, `Delete`, `AlterConfigs` | `Describe` on groups to display | `Describe` |
| Consumer | `Read`, `Describe` on topics to consume | `Read`, `Describe` on the `kaskade-` prefix | None |
| Sandbox population | `Create`, `Write`, `Describe` on topics to populate | None | None |

Use `User:<username>` for SASL/SCRAM or the certificate principal for mTLS, such
as `User:CN=kaskade`. Run the commands as an ACL administrator and configure
`admin-client.properties` for that administrator.

Full admin access:

```bash
kafka-acls.sh \
    --bootstrap-server "${BOOTSTRAP_SERVERS}" \
    --command-config admin-client.properties \
    --add \
    --allow-principal "User:<principal>" \
    --operation Describe \
    --cluster

kafka-acls.sh \
    --bootstrap-server "${BOOTSTRAP_SERVERS}" \
    --command-config admin-client.properties \
    --add \
    --allow-principal "User:<principal>" \
    --operation Describe \
    --operation DescribeConfigs \
    --operation Create \
    --operation Alter \
    --operation Delete \
    --operation AlterConfigs \
    --topic '*'

kafka-acls.sh \
    --bootstrap-server "${BOOTSTRAP_SERVERS}" \
    --command-config admin-client.properties \
    --add \
    --allow-principal "User:<principal>" \
    --operation Describe \
    --group '*'
```

Consumer access to one topic and Kaskade's ephemeral consumer groups:

```bash
kafka-acls.sh \
    --bootstrap-server "${BOOTSTRAP_SERVERS}" \
    --command-config admin-client.properties \
    --add \
    --allow-principal "User:<principal>" \
    --operation Read \
    --operation Describe \
    --topic '<topic-name>'

kafka-acls.sh \
    --bootstrap-server "${BOOTSTRAP_SERVERS}" \
    --command-config admin-client.properties \
    --add \
    --allow-principal "User:<principal>" \
    --operation Read \
    --operation Describe \
    --group kaskade- \
    --resource-pattern-type prefixed
```

Sandbox population access to all topics:

```bash
kafka-acls.sh \
    --bootstrap-server "${BOOTSTRAP_SERVERS}" \
    --command-config admin-client.properties \
    --add \
    --allow-principal "User:<principal>" \
    --operation Create \
    --operation Write \
    --operation Describe \
    --topic '*'
```

Narrow `--topic '*'` with literal topic names or prefixed resource patterns when
appropriate. See AWS's
[Apache Kafka ACL documentation](https://docs.aws.amazon.com/msk/latest/developerguide/msk-acls.html),
including the default `allow.everyone.if.no.acl.found` behavior.

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

See the
[Kafka client quick start for Confluent Cloud](https://docs.confluent.io/cloud/current/client-apps/config-client.html).

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

## Format-specific consumers

Local JSON, Avro, and Protobuf deserializers use raw framing by default. Their
repeatable options accept `framing`, `key.framing`, and `value.framing`. The
scoped property overrides the global property, allowing key and value framing
to differ. Framing is explicit; these deserializers do not infer it from payload
bytes. The Registry deserializer always uses Confluent framing.

### JSON consumer

Consume raw JSON without additional configuration:

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic -v json
```

For a JSON payload with Confluent's magic-byte and schema-ID envelope, select
Confluent framing explicitly. This removes the envelope and parses the JSON but
does not query Schema Registry:

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic \
        -k string -v json \
        --json value.framing=confluent
```

### Avro consumer

Consume using a `my-schema.avsc` schema file:

```bash
kaskade consumer -b my-kafka:9092 --earliest \
        -k string -v avro \
        -t my-avro-topic \
        --avro value=my-schema.avsc
```

For records produced with Confluent's five-byte framing, add
`--avro value.framing=confluent`. Use the unscoped
`--avro framing=confluent` when every selected Avro field has the same framing.

### Protobuf consumer

Install `protoc` with your platform's package manager. For example:

```bash
brew install protobuf                 # macOS
sudo apt install protobuf-compiler    # Debian or Ubuntu
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
kaskade consumer -b my-kafka:9092 --earliest \
        -k string -v protobuf \
        -t my-protobuf-topic \
        --protobuf descriptor=my-descriptor.desc \
        --protobuf value=mypackage.MyMessage
```

For Confluent-framed Protobuf, select its decoder explicitly:

```bash
kaskade consumer -b my-kafka:9092 -t my-protobuf-topic \
        -k string -v protobuf \
        --protobuf descriptor=my-descriptor.desc \
        --protobuf value=mypackage.MyMessage \
        --protobuf value.framing=confluent
```

See the
[Protocol Buffers documentation](https://protobuf.dev/programming-guides/techniques/#self-description)
for more about `FileDescriptorSet`.
