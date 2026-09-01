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

Override the configured interval for one admin session with `--refresh-interval`:

```bash
kaskade admin -b my-kafka:9092 --refresh-interval 10
kaskade admin -b my-kafka:9092 --refresh-interval 0
```

The command-line value takes precedence over `config.yaml`. As with the YAML setting, `0` disables auto-refresh and enabled intervals must be at least 5 seconds.

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
| Copy selected topic or record | `y` |
| Copy selected screen text | `Cmd+C` on macOS or `Ctrl+Shift+C` on Linux |
| Export selected record | `Ctrl+E` |
| Consume more records | `n` |
| Change record chunk size | `#` |

Help opens in a contextual window above the current screen and lists every effective shortcut alias. Navigate it with `j`/`k`, arrows, Page Up/Down, or `g`/`G`, then close it with `Esc`, `q`, `?`, or `F1`. The command palette includes this contextual Help window instead of Textual's generic Keys panel.

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
| Topics | `kaskade.topics.describe`, `.copy`, `.filter`, `.refresh`, `.create`, `.edit`, `.delete`, `.show-all` |
| Records | `kaskade.records.show`, `.copy`, `.export`, `.consume`, `.filter`, `.chunk-size`, `.show-all` |
| Dialogs | `kaskade.filter-topics.apply`, `kaskade.delete-topic.confirm`, `kaskade.filter-records.apply`, `kaskade.chunk-size.select` |
| Editors | `kaskade.create-topic.save`, `kaskade.edit-topic.save` |

Unknown binding IDs, invalid key names, and malformed configuration produce an in-app warning while Kaskade continues with its default bindings.

### Copy topics and consumed records

Select a topic in Admin mode or a consumed record in Consumer mode, then press `y` to copy the topic name or readable record JSON. Copy is also available in Topic Details, Record Details, contextual Help, and Commands, but is omitted from the Footer.

Selecting screen text is separate: use `Cmd+C` on macOS or `Ctrl+Shift+C` on Linux. `Ctrl+C` always quits Kaskade, even while text is selected.

#### OSC 52 compatibility

Kaskade uses [Textual's terminal clipboard API](https://textual.textualize.io/api/app/#textual.app.App.copy_to_clipboard), which sends an [OSC 52](https://github.com/tmux/tmux/wiki/Clipboard) request to the terminal emulator. Kaskade cannot detect whether the terminal accepted it, so a confirmation toast means the request was sent, not that the system clipboard was verified.

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

OSC 52 writes to the clipboard owned by the terminal emulator on the user's computer. It can therefore work when Kaskade runs through SSH or `kubectl exec -it`; the remote machine or pod does not need its own clipboard. Every intermediate layer must preserve the escape sequence. Terminal multiplexers such as tmux may require [additional clipboard configuration](https://github.com/tmux/tmux/wiki/Clipboard#quick-summary), and browser terminals or other relays may filter OSC 52.

### Export a consumed record

Select a record in consumer mode or open its details, then press `Ctrl+E` to export it as
JSON. Kaskade saves the file to the same destination as the Screenshot command: the
Downloads directory in a local terminal or a browser download when web-hosted. The export
includes the topic, partition, offset, date, headers, and the deserialized key and value with
their deserializer names. Export Record is omitted from the Footer; find it in contextual
Help or Commands.

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

If a configured key or value deserializer cannot decode an individual record, Kaskade
shows `⚠`, displays that field with its BYTES fallback, and keeps consuming. Record
details, copy, and export include the requested deserializer, fallback, and error. Hover
the warning cell to see the field, requested deserializer, fallback, and error in a
tooltip. The other field remains decoded normally.

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
and automatic token refresh. Credentials are discovered through the standard AWS
credential provider chain, so environment variables, shared AWS profiles (including
`AWS_PROFILE`), and IAM roles attached to AWS workloads are supported without passing
credentials to Kaskade.

See [Configure clients for IAM access control](https://docs.aws.amazon.com/msk/latest/developerguide/configure-clients-for-iam-access-control.html)
for the Amazon MSK broker and IAM policy requirements.

#### Required IAM authorization policy

Amazon MSK IAM authentication does not use Apache Kafka ACLs for authorization.
Kafka ACLs have no effect on IAM identities; attach an IAM policy to the user or
role whose credentials Kaskade discovers.

Kaskade operations require these `kafka-cluster` actions:

| Mode | Required actions |
| --- | --- |
| Admin browsing | `Connect`, `DescribeTopic`, `DescribeTopicDynamicConfiguration`, `DescribeGroup` |
| Admin topic changes | Admin browsing plus `CreateTopic`, `AlterTopic`, `DeleteTopic`, `AlterTopicDynamicConfiguration` |
| Consumer | `Connect`, `DescribeTopic`, `ReadData`, `DescribeGroup`, `AlterGroup` |
| Sandbox population | `Connect`, `CreateTopic`, `DescribeTopic`, `WriteData` |

The following policy enables all Kaskade admin and consumer features. Replace the
region, account, cluster name, and cluster UUID placeholders. Narrow the topic
wildcard when Kaskade should only access selected topics.

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

Consumer mode creates an ephemeral group named `kaskade-<uuid>`, which is why
`AlterGroup` can be limited to the `kaskade-*` group ARN. Admin mode needs
`DescribeGroup` on every group it should display. For read-only admin access,
remove `CreateTopic`, `AlterTopic`, `DeleteTopic`, and
`AlterTopicDynamicConfiguration`. For consumer-only access, retain `Connect`,
`DescribeTopic`, `ReadData`, `DescribeGroup`, and `AlterGroup` on the corresponding
cluster, topic, and `kaskade-*` group resources.

The sandbox population command creates topics and writes records, so use this
separate policy when populating MSK:

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

Schema Registry authorization is separate from Amazon MSK IAM authorization.
See AWS's [authorization action semantics](https://docs.aws.amazon.com/msk/latest/developerguide/kafka-actions.html)
and [common client policy use cases](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control-use-cases.html)
for action dependencies and resource formats.

#### Apache Kafka ACLs for SASL/SCRAM and mTLS

Keep the IAM policies above when Kaskade connects with `--aws region=<region>`.
Use Apache Kafka ACLs instead when the broker authenticates Kaskade with
SASL/SCRAM or mutual TLS. On Amazon MSK, Kafka ACLs do not authorize IAM
identities, and IAM policies do not replace the ACLs needed by a SCRAM or mTLS
principal.

Grant the authenticated Kafka principal the operations used by the selected
Kaskade mode:

| Mode | Topic ACLs | Group ACLs | Cluster ACLs |
| --- | --- | --- | --- |
| Admin browsing | `Describe`, `DescribeConfigs` | `Describe` on groups to display | `Describe` |
| Admin topic changes | Admin browsing plus `Create`, `Alter`, `Delete`, `AlterConfigs` | None beyond admin browsing | None beyond admin browsing |
| Consumer | `Read`, `Describe` on topics to consume | `Read`, `Describe` on the `kaskade-` prefix | None |
| Sandbox population | `Create`, `Write`, `Describe` on topics to populate | None | None |

For SASL/SCRAM, the principal is normally `User:<username>`. For mTLS, use the
principal derived from the client certificate, such as `User:CN=kaskade`. Run
the following commands as an ACL administrator, replacing the bootstrap servers,
principal, and command configuration file. The command configuration must contain
the properties that authenticate `kafka-acls.sh` to the cluster.

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

Replace `--topic '*'` with literal topic names or a prefixed resource pattern
when broader access is not required. On Amazon MSK,
`allow.everyone.if.no.acl.found` is `true` by default; after an ACL exists for a
resource, only explicitly authorized principals can access it. Review AWS's
[Apache Kafka ACL documentation](https://docs.aws.amazon.com/msk/latest/developerguide/msk-acls.html)
before applying ACLs to an existing cluster.

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
kaskade consumer -b my-kafka:9092 --earliest \
        -k string -v avro \
        -t my-avro-topic \
        --avro value=my-schema.avsc
```

Local-schema Avro deserialization treats payloads as raw Avro by default. For records
produced with Confluent's five-byte framing, add `--avro framing=confluent`. Framing is
explicit because a valid raw Avro payload may also begin with a zero byte.

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
kaskade consumer -b my-kafka:9092 --earliest \
        -k string -v protobuf \
        -t my-protobuf-topic \
        --protobuf descriptor=my-descriptor.desc \
        --protobuf value=mypackage.MyMessage
```

See the [Protocol Buffers documentation](https://protobuf.dev/programming-guides/techniques/#self-description) for more about `FileDescriptorSet`.
