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

Deserializer settings are repeatable `property=value` options: `--bytes` and
`--fallback` control byte encoding, `--json`/`--avro`/`--protobuf` configure local
deserializers, and `--registry` configures Schema Registry. See the detailed
examples below.

## Application settings and controls

On Linux and macOS, Kaskade reads `$XDG_CONFIG_HOME/kaskade/settings.yaml`. If
`XDG_CONFIG_HOME` is not set, it reads `~/.config/kaskade/settings.yaml`. Set
`KASKADE_SETTINGS` to use a different file.

Copy the complete example to the default location before customizing it:

```bash
mkdir -p ~/.config/kaskade
cp examples/settings.yaml ~/.config/kaskade/settings.yaml
```

### Themes

Kaskade includes the original `eva01` Unit-01-inspired theme and the darker
`eva01-berserk` variant, which is the default. Set another default in `settings.yaml`:

```yaml
theme: dracula
```

Override the configured theme for one session at launch:

```bash
kaskade admin -b my-kafka:9092 --theme dracula
```

While Kaskade is running, press `:` (or `Ctrl+P`) and select a theme from the
Commands window. Command-line and in-application theme changes apply only to the
current session.

### Admin auto-refresh

Admin mode refreshes every 30 seconds, pauses outside the topic list, and
refreshes after returning. Press `Ctrl+R` to refresh immediately.

Configure the interval in Kaskade's `settings.yaml`:

```yaml
admin:
  refresh-interval: 30
```

Use `0` to disable auto-refresh. Other values must be at least 5 seconds;
missing or invalid values use the default, with an in-app warning when invalid.

Override the configured interval for one admin session with `--refresh-interval`:

```bash
kaskade admin -b my-kafka:9092 --refresh-interval 10
kaskade admin -b my-kafka:9092 --refresh-interval 0
```

The command-line value takes precedence and follows the same validation rules.

Topic Details keeps partition, replica, in-sync replica, approximate record,
consumer-group, member, and approximate lag totals visible above its tabs.

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
| Previous or next record in Record Details | `N`/`p` or `n` |
| Save Create Topic or Edit Topic | `Ctrl+S`, `Ctrl+Shift+S`, or `F2` |

Help lists every contextual shortcut alias. Navigate with the standard keys and
close with `Esc`, `q`, `?`, or `F1`. The Commands palette links to the same Help.

Plain-character application shortcuts do not intercept typing in filter and
editor fields.

Terminals without distinct shifted-control key encoding may treat
`Ctrl+Shift+S` as `Ctrl+S`; both bindings save. Enter keeps its normal submission
or selection behavior within form controls.

#### Custom keymap

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
| Record Details | `kaskade.record-details.previous`, `.next`, `.close` |
| Dialogs | `kaskade.filter-topics.apply`, `kaskade.delete-topic.confirm`, `kaskade.filter-records.apply`, `kaskade.chunk-size.select` |
| Editors | `kaskade.create-topic.save`, `kaskade.edit-topic.save` |

Unknown binding IDs, invalid key names, and malformed configuration produce an
in-app warning while Kaskade continues with its default bindings.

### Logs

Kaskade writes logs to `$XDG_STATE_HOME/kaskade/kaskade.log`. If
`XDG_STATE_HOME` is not set, it writes to
`~/.local/state/kaskade/kaskade.log`.

The active log rotates at 5 MiB, and Kaskade retains three backups named
`kaskade.log.1` through `kaskade.log.3`. This bounds total log storage to
approximately 20 MiB.

### Clipboard and record export

Select a topic in Admin mode or a consumed record in Consumer mode, then press
`y` to copy the topic name or readable record JSON. Record Details separates the
key, value, ordered headers, and complete JSON into tabs while keeping the total
raw payload size, partition, offset, and timestamp visible. The topic remains in
the border title. In that modal, `y` copies the active tab's headers array, key
object, value object, or complete record object. Copy is also available in Topic
Details, contextual Help, and Commands, but is omitted from the Footer.

The Consumer records table shows the same total raw message size in its Size
column.

Key, value, and the selected header show compact deserializer, schema, and
original payload-size diagnostics above their complete content. Explicit BYTES
encoding appears beside the deserializer. Payload size appears in KB below 1 MB
and in MB at or above that threshold. Deserialization failures use a highlighted
error panel that identifies the BYTES fallback encoding.

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

#### Export a consumed record

Press `Ctrl+E` from the records table or any Record Details tab to export the
complete record JSON. Local terminals save to Downloads; web-hosted sessions use
a browser download. Export Record appears in Help and Commands, not the Footer.

The complete JSON tab, records-table and JSON-tab copies, and exports share the
contract in
[`schemas/consumer-record.schema.json`](schemas/consumer-record.schema.json),
which uses JSON Schema Draft 2020-12. Examples cover:

- [bytes](examples/consumer-record-byte.json)
- [deserialization errors and byte fallback](examples/consumer-record-error.json)
- [strings](examples/consumer-record-string.json)
- [JSON](examples/consumer-record-json.json)
- [Confluent Schema Registry](examples/consumer-record-confluent.json)
- [native Apicurio Registry](examples/consumer-record-apicurio.json)

Registry metadata is resolved independently for keys and values. Native Apicurio
metadata always contains its provider and ID; registration details appear when
the Registry can resolve them unambiguously. Headers remain ordered, timestamps
use UTC ISO 8601 milliseconds, and tombstones use `content: null`. Enter lowercase
`null` in a key, value, or header filter to match null content.

## Consumer behavior

### Configure byte presentation

BYTES content defaults to Base64. Configure it globally or per field:

```bash
--bytes encoding=base64 \
--bytes key.encoding=hex \
--bytes value.encoding=byte-array
```

Encodings are `base64`, `hex`, `byte-array`, and `escaped`; values are
case-insensitive and underscores normalize to hyphens. Scoped settings override
the global encoding. `--bytes` does not affect deserialization fallbacks, and
null BYTES fields omit encoding metadata.

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

On a recognized deserialization failure, Kaskade shows `⚠`, presents the raw
field through BYTES, and keeps consuming. Configure key, value, and header
fallback encoding independently from explicit BYTES fields:

```bash
--fallback encoding=hex
```

`--fallback` accepts only the global `encoding` property; key and value scopes are
not supported. It defaults to Base64. The diagnostic is a sibling of the
requested deserializer:

```json
{
  "content": "/w==",
  "deserializer": {
    "type": "REGISTRY"
  },
  "error": {
    "message": "Unexpected magic byte -1",
    "fallback": {
      "type": "BYTES",
      "encoding": "BASE64"
    }
  }
}
```

Every successful header remains a compact `{key, value}` object. If a header is
not valid UTF-8, its raw content uses the global fallback encoding and the header
adds the same top-level error metadata:

```json
{
  "key": "binary",
  "value": "/w==",
  "error": {
    "message": "Invalid UTF-8 payload",
    "fallback": {
      "type": "BYTES",
      "encoding": "BASE64"
    }
  }
}
```

Details, copy, export, and warning tooltips preserve the diagnostic while the
other field remains decoded normally.

## Connections and security

### Schema Registry

Connect to a Schema Registry:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry url=http://my-schema-registry:8081
```

`provider` accepts `confluent` or `apicurio` case-insensitively and defaults to
`confluent`. Confluent client properties retain their existing names and are
forwarded unchanged.

With Confluent Schema Registry, the Registry deserializer detects Avro, JSON
Schema, and Protobuf from each record's schema ID. Protobuf messages are resolved
dynamically from the registry, including referenced schemas, so no local descriptor
file is required.

See the
[Confluent Schema Registry client documentation](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html#schemaregistry-client)
for additional Schema Registry settings.

Kaskade forwards every repeated `--registry property=value` setting to the
Schema Registry client. For an OAuth/OIDC Registry using the client credentials
flow:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k string -v registry \
        --registry url=${SCHEMA_REGISTRY_URL} \
        --registry bearer.auth.credentials.source=OAUTHBEARER \
        --registry bearer.auth.issuer.endpoint.url=${OAUTH_TOKEN_URL} \
        --registry bearer.auth.client.id=${OAUTH_CLIENT_ID} \
        --registry bearer.auth.client.secret=${OAUTH_CLIENT_SECRET} \
        --registry bearer.auth.scope=${OAUTH_SCOPE} \
        --registry bearer.auth.logical.cluster=${SR_LOGICAL_CLUSTER} \
        --registry bearer.auth.identity.pool.id=${IDENTITY_POOL_ID}
```

The logical cluster and identity pool settings are deployment-specific. The
Schema Registry client validates property names, values, and required settings.

#### Apicurio Registry

Use `provider=apicurio` to select the native Apicurio Registry v3 API. Kaskade
accepts the applicable official `apicurio.registry.*` deserializer properties;
it does not infer a provider from those names or accept generic aliases:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry provider=apicurio \
        --registry apicurio.registry.url=http://my-apicurio-registry:8081/apis/registry/v3 \
        --registry apicurio.registry.use-id=contentId
```

OAuth client credentials use Apicurio names as well:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry provider=apicurio \
        --registry apicurio.registry.url=${APICURIO_REGISTRY_URL} \
        --registry apicurio.registry.auth.service.token.endpoint=${OAUTH_TOKEN_URL} \
        --registry apicurio.registry.auth.client.id=${OAUTH_CLIENT_ID} \
        --registry apicurio.registry.auth.client.secret=${OAUTH_CLIENT_SECRET}
```

The native client also accepts Apicurio's Basic authentication, retry, cache,
proxy, and PEM TLS properties. Serializer-only properties, including artifact
selection and auto-registration settings, are rejected. JKS and PKCS12 stores,
header-based IDs, custom ID handlers, and legacy eight-byte framing are not
supported. See the
[Apicurio Registry client configuration reference](https://www.apicur.io/registry/docs/apicurio-registry/3.3.x/getting-started/assembly-configuring-kafka-client-serdes.html).

To use Apicurio's Confluent-compatible endpoint instead, leave the provider as
`confluent` and configure the existing Confluent `url` property:

```bash
--registry url=http://my-apicurio-registry:8081/apis/ccompat/v7
```

### SSL encryption

```bash
kaskade admin -b my-kafka:9092 --kafka security.protocol=SSL
```

See
[Configure librdkafka client](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client)
for SSL encryption and authentication settings.

### Client configuration file

Both admin and consumer modes accept an INI configuration file. Kafka client
properties belong in `[kafka]`, consumer Schema Registry properties in
`[registry]`, and Amazon MSK IAM settings in `[aws]`. Any section may be omitted
when it is not needed:

```bash
kaskade admin \
    --config-file client.ini

kaskade consumer \
    -t my-topic \
    --config-file client.ini \
    -v registry
```

Keys and values remain strings and dotted client property names need no quoting.
Blank lines and lines beginning with `#` or `;` are ignored. See
[examples/client.ini](examples/client.ini) for a Kafka, Schema Registry, and AWS
example:

```ini
[kafka]
bootstrap.servers = my-msk-bootstrap:9098
client.id = kaskade

[registry]
url = https://my-schema-registry:8081
basic.auth.user.info = replace-with-your-api-key:replace-with-your-api-secret

[aws]
region = us-east-1
```

The `[kafka]` section contains `confluent-kafka` properties. The `[registry]`
section contains Confluent client properties by default or native Apicurio
properties when `provider=apicurio`. Kaskade UI, admin, and keymap settings remain in
`settings.yaml` as documented above. Both commands require a non-empty
`bootstrap.servers` after Kafka properties are merged. It can come from
`--config-file`, an inline property, or the dedicated option:

```bash
kaskade admin --kafka bootstrap.servers=my-kafka:9092
kaskade consumer -t my-topic --kafka bootstrap.servers=my-kafka:9092
```

`-b/--bootstrap-servers` remains the most concise choice for ordinary commands
and overrides a value from Kafka client configuration. For example, this uses
`override-kafka:9092` while retaining the other file and inline properties:

```bash
kaskade admin \
    --config-file client.ini \
    --kafka client.id=temporary-kaskade \
    -b override-kafka:9092
```

Configuration precedence, from lowest to highest, is:

1. Properties loaded from the matching `[kafka]`, `[registry]`, or `[aws]`
   section of `--config-file`.
2. Repeated `--kafka property=value`, `--registry property=value`, and
   `--aws property=value` options.
3. When supplied, `-b/--bootstrap-servers` for `bootstrap.servers`.
4. Resolved AWS settings configure the Amazon MSK IAM authentication properties.
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

Kaskade honors `group.id` from Kafka client configuration. When it is omitted,
Kaskade creates an ephemeral `kaskade-<uuid>` group.
`--earliest` and explicit `--partition` reads use direct partition assignment;
they do not use committed offsets. Set `group.id` explicitly when the Kafka
principal is restricted to a specific consumer group. For read-only admin access, remove
`CreateTopic`, `AlterTopic`, `DeleteTopic`, `AlterTopicDynamicConfiguration`,
and `ReadData` from the topic statement, then remove the
`UseKaskadeConsumerGroups` statement.

See AWS's [authorization action semantics](https://docs.aws.amazon.com/msk/latest/developerguide/kafka-actions.html)
and [common client policy use cases](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control-use-cases.html)
for dependencies and resource formats.

### Kafka ACLs

For SASL/SCRAM and mTLS connections, grant the Kafka principal these operations:

| Mode | Topic ACLs | Group ACLs | Cluster ACLs |
| --- | --- | --- | --- |
| Admin (read only) | `Describe`, `DescribeConfigs` | `Describe` on groups to display | `Describe` |
| Admin (full access) | `Describe`, `DescribeConfigs`, `Create`, `Alter`, `Delete`, `AlterConfigs` | `Describe` on groups to display | `Describe` |
| Consumer | `Read`, `Describe` on topics to consume | `Read`, `Describe` on the configured `group.id` or `kaskade-` prefix | — |

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

Narrow `--topic '*'` with literal topic names or prefixed resource patterns when
appropriate. See AWS's
[Apache Kafka ACL documentation](https://docs.aws.amazon.com/msk/latest/developerguide/msk-acls.html),
including the default `allow.everyone.if.no.acl.found` behavior.

### Confluent Cloud

Admin:

```bash
kaskade admin -b ${BOOTSTRAP_SERVERS} \
        --kafka security.protocol=SASL_SSL \
        --kafka sasl.mechanism=PLAIN \
        --kafka sasl.username=${CLUSTER_API_KEY} \
        --kafka sasl.password=${CLUSTER_API_SECRET}
```

Consumer:

```bash
kaskade consumer -b ${BOOTSTRAP_SERVERS} -t my-avro-topic \
        -k string -v registry \
        --kafka security.protocol=SASL_SSL \
        --kafka sasl.mechanism=PLAIN \
        --kafka sasl.username=${CLUSTER_API_KEY} \
        --kafka sasl.password=${CLUSTER_API_SECRET} \
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

The `--key` and `--value` format names are case-insensitive and normalize to the
lowercase choices shown in CLI help.

Local JSON, Avro, and Protobuf deserializers use `raw` framing by default. Their
repeatable options accept `framing`, `key.framing`, and `value.framing`, with
case-insensitive values `raw`, `apicurio`, or `confluent`. The scoped property
overrides the global property, allowing key and value framing to differ. Framing
is explicit; these deserializers do not infer it from payload bytes. The Registry
deserializer selects framing from its configured provider.

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

For an Apicurio-produced JSON payload, use the corresponding framing without
querying the registry:

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic \
        -k string -v json \
        --json value.framing=apicurio
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
Use `apicurio` instead for records produced by Apicurio serializers.

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

Use `--protobuf value.framing=apicurio` for Apicurio-produced Protobuf. It
removes both the registry ID envelope and Apicurio's message-type reference
before decoding with the local descriptor.

See the
[Protocol Buffers documentation](https://protobuf.dev/programming-guides/techniques/#self-description)
for more about `FileDescriptorSet`.
