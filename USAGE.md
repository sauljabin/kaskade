# Usage

Kaskade has three modes: `kaskade admin` manages topics and shows consumer
groups, `kaskade consumer` reads records, and `kaskade producer` writes them.
This guide shows how to connect first, then each mode, then the settings they
share.

## Contents

- [Common commands](#common-commands)
  - [Multiple bootstrap servers](#multiple-bootstrap-servers)
  - [Short command name](#short-command-name)
- [Configuration files](#configuration-files)
- [Connect to Kafka](#connect-to-kafka)
  - [Client configuration file](#client-configuration-file)
  - [Configuration precedence](#configuration-precedence)
  - [SSL encryption](#ssl-encryption)
  - [Schema Registry](#schema-registry)
  - [Amazon MSK with IAM authentication](#amazon-msk-with-iam-authentication)
  - [Kafka ACLs](#kafka-acls)
  - [Confluent Cloud](#confluent-cloud)
- [Admin](#admin)
  - [Browse and change topics](#browse-and-change-topics)
  - [Topic Details](#topic-details)
  - [Admin auto-refresh](#admin-auto-refresh)
  - [Admin shortcuts](#admin-shortcuts)
- [Consumer](#consumer)
  - [Consume records](#consume-records)
  - [Byte presentation](#byte-presentation)
  - [Decode with schema files](#decode-with-schema-files)
  - [Decode with a Schema Registry](#decode-with-a-schema-registry)
  - [Choose the starting position](#choose-the-starting-position)
  - [Deserialization failures](#deserialization-failures)
  - [Record Details, copy, and export](#record-details-copy-and-export)
  - [Consumer configuration](#consumer-configuration)
  - [Consumer shortcuts](#consumer-shortcuts)
- [Producer](#producer)
  - [Compose and produce](#compose-and-produce)
  - [Serializers](#serializers)
  - [Produce with schema files](#produce-with-schema-files)
  - [Produce with a Schema Registry](#produce-with-a-schema-registry)
  - [Register schemas](#register-schemas)
  - [Load a draft from a file](#load-a-draft-from-a-file)
  - [Producer configuration](#producer-configuration)
  - [Producer shortcuts](#producer-shortcuts)
- [Application settings](#application-settings)
  - [Themes](#themes)
  - [Custom themes](#custom-themes)
  - [Operation timeouts](#operation-timeouts)
  - [Keyboard shortcuts](#keyboard-shortcuts)
  - [Custom keymap](#custom-keymap)
  - [Clipboard](#clipboard)
  - [Kantrip profile](#kantrip-profile)
  - [Logs](#logs)
- [Agent skill and cheatsheet](#agent-skill-and-cheatsheet)

## Common commands

Administer, consume, and produce:

```bash
kaskade admin -b my-kafka:9092
kaskade consumer -b my-kafka:9092 -t my-topic -k string -v json
kaskade producer -b my-kafka:9092 -t my-topic -k string -v json
```

`kaskade admin --help`, `kaskade consumer --help`, and
`kaskade producer --help` list every option with more examples.

### Multiple bootstrap servers

Repeat `-b/--bootstrap-server` or pass a comma-separated list; both produce the
same `bootstrap.servers`, in order:

```bash
kaskade admin -b my-kafka:9092 -b my-kafka:9093
kaskade admin -b my-kafka:9092,my-kafka:9093
```

Empty entries and duplicate brokers are rejected.

### Short command name

Kaskade doesn't install a shortcut. If you want a shorter command, `kas` is the
suggested name. Make it a symlink in a directory on your `PATH`, such as
`~/.local/bin`:

```bash
ln -s "$(command -v kaskade)" ~/.local/bin/kas
```

Then run `kas --version`. A symlink works in every shell and in scripts, and
[Kantrip](https://github.com/sauljabin/kantrip) recognizes it as Kaskade, so a
Kantrip session's connection applies to `kas` too.

## Configuration files

Kaskade uses two files, and they aren't interchangeable:

| File | Purpose | Loading behavior | Typical contents |
| --- | --- | --- | --- |
| `client.ini` | How to connect to a cluster | Loaded only when passed with `--config-file` | Kafka, Schema Registry, and AWS IAM properties |
| `settings.yaml` | How Kaskade behaves | Discovered and loaded automatically on every run | Theme, custom themes, keybindings, Admin auto-refresh interval, and operation timeouts |

You can keep one `client.ini` per cluster, such as `development.ini` and
`production.ini`, and share one `settings.yaml` between them. A `client.ini`
may hold SASL passwords or Registry credentials, so restrict its permissions
and don't commit it. Leave AWS credentials in the standard AWS credential
provider chain rather than in either file.

[Connect to Kafka](#connect-to-kafka) covers `client.ini`, and
[Application settings](#application-settings) covers `settings.yaml`.

## Connect to Kafka

Every mode connects the same way, with the options in this section.

### Client configuration file

All three commands accept an INI connection file through `--config-file`.
Kafka client properties belong in `[kafka]`, Schema Registry properties for the
consumer and producer in `[registry]`, and Amazon MSK IAM settings in `[aws]`.
Any section may be omitted when it is not needed.

```bash
kaskade admin --config-file client.ini
kaskade consumer --config-file client.ini -t my-topic -v registry
kaskade producer --config-file client.ini -t my-topic -v registry
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
properties when `provider=apicurio`.

Every command requires a non-empty `bootstrap.servers` after Kafka properties
are merged. It can come from `--config-file`, an inline property, or
`-b/--bootstrap-server`:

```bash
kaskade admin --kafka bootstrap.servers=my-kafka:9092
kaskade consumer -t my-topic --kafka bootstrap.servers=my-kafka:9092
```

`-b` is the most concise choice and overrides a value from Kafka client
configuration. This uses `override-kafka:9092` and keeps the other file and
inline properties:

```bash
kaskade admin \
    --config-file client.ini \
    --kafka client.id=temporary-kaskade \
    -b override-kafka:9092
```

### Configuration precedence

From lowest to highest:

1. Properties from the matching `[kafka]`, `[registry]`, or `[aws]` section of
   `--config-file`.
2. Repeated `--kafka property=value`, `--registry property=value`, and
   `--aws property=value` options.
3. In producer mode, the `--acks`, `--compression`, and `--idempotence`
   options you pass; see [Producer configuration](#producer-configuration).
4. `-b/--bootstrap-server` for `bootstrap.servers`.
5. Resolved AWS settings, which configure the Amazon MSK IAM authentication
   properties.
6. In consumer mode, `--earliest` for `auto.offset.reset=earliest`.

### SSL encryption

```bash
kaskade admin -b my-kafka:9092 --kafka security.protocol=SSL
```

See
[Configure librdkafka client](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client)
for SSL encryption and authentication settings.

### Schema Registry

The consumer and the producer connect to a Registry with the same
`--registry property=value` options or `[registry]` section. The examples below
use the consumer; [Decode with a Schema Registry](#decode-with-a-schema-registry)
and [Produce with a Schema Registry](#produce-with-a-schema-registry) cover what
each mode does with it.

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry url=http://my-schema-registry:8081
```

`provider` accepts `confluent` or `apicurio` case-insensitively and defaults to
`confluent`. Kaskade passes every other `--registry property=value` setting to
the Schema Registry client unchanged, under its usual name. See the
[Confluent Schema Registry client documentation](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html#schemaregistry-client)
for more settings.

For an OAuth/OIDC Registry using the client credentials flow:

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
accepts its explicit `apicurio.registry.*` properties; it does not infer a
provider from those names or accept generic aliases:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry provider=apicurio \
        --registry apicurio.registry.url=http://my-apicurio-registry:8081/apis/registry/v3 \
        --registry apicurio.registry.use-id=contentId
```

OAuth client credentials use Apicurio names as well. Put secrets in a private
configuration file instead of command arguments:

```ini
[registry]
provider = apicurio
apicurio.registry.url = https://registry.example.com/apis/registry/v3
apicurio.registry.tls.certificates = /private/registry-and-idp-ca.pem
apicurio.registry.auth.service.token.endpoint = https://idp.example.com/token
apicurio.registry.auth.client.id = registry-reader
apicurio.registry.auth.client.secret = replace-with-client-secret
apicurio.registry.auth.client.scope = registry.read
```

```bash
kaskade consumer --config-file private-client.ini \
        -b my-kafka:9092 -t my-avro-topic -k registry -v registry
```

Registry TLS and OAuth token-endpoint TLS use separate contexts, and a Registry
client certificate is never sent to the token endpoint. For compatibility with
Apicurio's Java client, the official `apicurio.registry.tls.certificates`
property supplies the CA bundle for both endpoints, so include both chains in
it when they differ. Native Apicurio also supports Basic authentication with
private CA trust and unencrypted PEM mTLS. OAuth access tokens are cached until
their reported expiry and refreshed in the same running client; one `401` also
forces one token refresh and retry.

The native client also accepts retry, cache, and proxy properties. JKS and
PKCS12 stores, header-based IDs, custom ID handlers, and legacy eight-byte
framing are not supported. See the
[Apicurio Registry client configuration reference](https://www.apicur.io/registry/docs/apicurio-registry/3.3.x/getting-started/assembly-configuring-kafka-client-serdes.html).

To use Apicurio's Confluent-compatible endpoint instead, leave the provider as
`confluent` and configure the Confluent `url` property:

```bash
--registry url=http://my-apicurio-registry:8081/apis/ccompat/v7
```

### Amazon MSK with IAM authentication

Pass the AWS region to enable IAM authentication in any mode:

```bash
kaskade admin -b ${AWS_MSK_BOOTSTRAP_SERVERS} --aws region=us-east-1
kaskade consumer -b ${AWS_MSK_BOOTSTRAP_SERVERS} -t my-topic --aws region=us-east-1
kaskade producer -b ${AWS_MSK_BOOTSTRAP_SERVERS} -t my-topic --aws region=us-east-1
```

Kaskade configures `security.protocol=SASL_SSL`, `sasl.mechanism=OAUTHBEARER`,
and automatic token refresh. Credentials come from the standard AWS credential
provider chain, so environment variables, shared AWS profiles (including
`AWS_PROFILE`), and IAM roles attached to AWS workloads work without passing
credentials to Kaskade.

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
| Producer | `Connect`, `DescribeTopic`, `WriteData`; `CreateTopic` only for broker auto-creation; `WriteDataIdempotently` on the cluster with `--idempotence true` |

Example identity policies:

- [Admin](examples/aws-msk-iam-admin-policy.json)
- [Consumer](examples/aws-msk-iam-consumer-policy.json)
- [Producer](examples/aws-msk-iam-producer-policy.json)
- [Admin and consumer](examples/aws-msk-iam-admin-consumer-policy.json)

Replace the region, account, cluster name, and cluster UUID placeholders, and
narrow the topic wildcard when appropriate. If `group.id` is configured,
replace the `kaskade-*` group pattern with that group ID or a suitable
wildcard. For read-only admin access with the admin and consumer policy, remove
`CreateTopic`, `AlterTopic`, `DeleteTopic`, `AlterTopicDynamicConfiguration`,
and `ReadData` from the topic statement, then remove the
`UseKaskadeConsumerGroups` statement.

For cross-account access, the cluster owner must also add a
[resource-based cluster policy](https://docs.aws.amazon.com/msk/latest/developerguide/security_iam_service-with-iam-resource-based-policies.html)
that grants the client account or role the corresponding `kafka-cluster`
permissions.

See AWS's [authorization action semantics](https://docs.aws.amazon.com/msk/latest/developerguide/kafka-actions.html)
and [common client policy use cases](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control-use-cases.html)
for dependencies and resource formats.

### Kafka ACLs

For SASL/SCRAM and mTLS connections, grant the Kafka principal these operations:

| Mode | Topic ACLs | Group ACLs |
| --- | --- | --- |
| Admin (read only) | `Describe`, `DescribeConfigs` | `Describe` on groups to display |
| Admin (full access) | `Describe`, `DescribeConfigs`, `Create`, `Alter`, `Delete`, `AlterConfigs` | `Describe` on groups to display |
| Consumer | `Read`, `Describe` on topics to consume | `Read`, `Describe` on the configured `group.id` or `kaskade-` prefix |
| Producer | `Write`, `Describe` on the topic; `Create` only for broker auto-creation | None |

`Write` implies `Describe`. With `--idempotence true`, brokers older than Kafka 3.0
also need cluster `IdempotentWrite`.

Admin shows only the consumer groups the principal can describe. A principal
with cluster `Describe` lists every group; Kaskade skips the ones it cannot
describe instead of reporting a failed refresh.

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

Producer access to one topic:

```bash
kafka-acls.sh \
    --bootstrap-server "${BOOTSTRAP_SERVERS}" \
    --command-config admin-client.properties \
    --add \
    --allow-principal "User:<principal>" \
    --operation Write \
    --operation Describe \
    --topic '<topic-name>'
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

The producer takes the same options: replace `kaskade consumer` with
`kaskade producer`.

See the
[Kafka client quick start for Confluent Cloud](https://docs.confluent.io/cloud/current/client-apps/config-client.html).

## Admin

### Browse and change topics

`kaskade admin` lists the cluster's topics with their partitions, replicas,
record counts, and consumer groups:

```bash
kaskade admin -b my-kafka:9092
```

Filter the list with `/`, open [Topic Details](#topic-details) with `d` or
`Enter`, and create, edit, or delete topics without leaving the list. Create
Topic and Edit Topic save with `Ctrl+S`; [Admin shortcuts](#admin-shortcuts)
lists every key.

### Topic Details

Topic Details keeps partition, replica, in-sync replica, approximate record,
consumer-group, member, and approximate lag totals visible above its tabs.
The Partitions tab includes each partition's earliest and end offsets. Group
Offsets shows committed and end offsets with lag for every group partition.
End is the next offset after the partition's latest record; Committed is the
group's saved next offset to consume. Lag is their non-negative difference.
Only partitions with available committed offsets appear in Group Offsets.

### Admin auto-refresh

Admin mode refreshes every 30 seconds, pauses outside the topic list, and
refreshes after returning. Press `Ctrl+R` to refresh immediately.

Configure the interval in `settings.yaml`:

```yaml
admin:
  refresh-interval: 30
```

Use `0` to disable auto-refresh. Other values must be at least 5 seconds;
missing or invalid values use the default, with an in-app warning when invalid.

Override the configured interval for one session with `--refresh-interval`,
which follows the same rules:

```bash
kaskade admin -b my-kafka:9092 --refresh-interval 10
kaskade admin -b my-kafka:9092 --refresh-interval 0
```

Admin's read and write deadlines are in
[Operation timeouts](#operation-timeouts).

### Admin shortcuts

These add to the [shortcuts every mode shares](#keyboard-shortcuts). The
binding ID is the name to use in a [custom keymap](#custom-keymap).

| Action | Shortcut | Binding ID |
| --- | --- | --- |
| Filter topics | `/` or `Ctrl+F` | `kaskade.topics.filter` |
| Show all topics after filtering | `Esc` | `kaskade.topics.show-all` |
| Describe a topic | `d` or `Enter` | `kaskade.topics.describe` |
| Create a topic | `n` or `Ctrl+N` | `kaskade.topics.create` |
| Edit a topic | `e` or `Ctrl+E` | `kaskade.topics.edit` |
| Delete a topic | `Ctrl+D` | `kaskade.topics.delete` |
| Refresh topics | `Ctrl+R` | `kaskade.topics.refresh` |
| Copy the selected topic name | `y` | `kaskade.topics.copy` |
| Save Create Topic or Edit Topic | `Ctrl+S`, `Ctrl+Shift+S`, or `F2` | `kaskade.create-topic.save`, `kaskade.edit-topic.save` |
| Apply the topic filter or confirm a deletion | `Enter` | `kaskade.filter-topics.apply`, `kaskade.delete-topic.confirm` |

## Consumer

### Consume records

`kaskade consumer` reads records from the topic given with `-t`, and `-k` and
`-v` choose how to deserialize the key and the value:

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic -k json -v json
```

The deserializers are `bytes`, `boolean`, `string`, `long`, `integer`,
`double`, `float`, `json`, `avro`, `protobuf`, and `registry`. Both `-k/--key`
and `-v/--value` default to `string`, as in the producer. A key or value that
isn't valid UTF-8 is a [deserialization failure](#deserialization-failures): it
shows as bytes next to the error, and consuming continues. The names are
case-insensitive and normalize to the lowercase choices shown in CLI help.

Deserializer settings are repeatable `property=value` options: `--bytes` and
`--fallback` control byte encoding, `--json`, `--avro`, and `--protobuf`
configure the local deserializers, and `--registry` configures Schema Registry.
The sections below cover each one.

### Byte presentation

`-k bytes` and `-v bytes` show content as Base64 by default. `--bytes` changes
the encoding globally or per field, and needs at least one field that uses
`bytes`:

```bash
-k bytes -v bytes \
--bytes encoding=base64 \
--bytes key.encoding=hex \
--bytes value.encoding=byte-array
```

Encodings are `base64`, `hex`, `byte-array`, and `escaped`; values are
case-insensitive and underscores normalize to hyphens. Scoped settings override
the global encoding. `--bytes` does not affect
[deserialization fallbacks](#deserialization-failures), and null BYTES fields
omit encoding metadata.

### Decode with schema files

Local JSON, Avro, and Protobuf deserializers use `raw` framing by default. Their
repeatable options accept `framing`, `key.framing`, and `value.framing`, with
case-insensitive values `raw`, `apicurio`, or `confluent`. The scoped property
overrides the global one, so key and value framing can differ. Framing is
explicit: these deserializers never infer it from payload bytes, and they never
query a registry.

#### JSON

Consume raw JSON without additional configuration:

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic -v json
```

For JSON with Confluent's magic-byte and schema-ID envelope, or one produced by
Apicurio, select the framing to remove the envelope before parsing:

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic \
        -k string -v json \
        --json value.framing=confluent
```

Use `--json value.framing=apicurio` for Apicurio-produced JSON.

Add a JSON Schema file to validate each record after framing is removed:

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic \
        -k string -v json \
        --json value=my-schema.json
```

A record that doesn't match is a
[deserialization failure](#deserialization-failures) for that field only: it
falls back to BYTES with `JSON Schema validation failed: …`, naming the path and
rule but never the value. Each `$ref` resolves against files next to the
schema, and remote URLs are never fetched. An unreadable or invalid schema
fails before the TUI opens.

#### Avro

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

#### Protobuf

`--protobuf` takes the schema as `source=` (a `.proto` file) or `descriptor=` (a
descriptor set), never both, and `key=` or `value=` the full message name.
Kaskade compiles a source with its bundled `protoc`; its imports resolve from
files next to it and the well-known types:

```bash
kaskade consumer -b my-kafka:9092 --earliest \
        -k string -v protobuf \
        -t my-protobuf-topic \
        --protobuf source=my-proto.proto \
        --protobuf value=mypackage.MyMessage
```

When a source imports files from other folders, add them with `include=`. It
works only with `source=`, can be repeated or comma-separated like `-b`, and is
searched in order after the source's folder and before the well-known types:

```bash
kaskade consumer -b my-kafka:9092 --earliest \
        -k string -v protobuf \
        -t my-protobuf-topic \
        --protobuf source=protos/orders/order.proto \
        --protobuf include=protos/common \
        --protobuf include=vendor/protos \
        --protobuf value=mypackage.Order
```

To use a descriptor set instead, install `protoc` with your platform's package
manager:

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

Consume using `my-descriptor.desc`, here with Confluent framing:

```bash
kaskade consumer -b my-kafka:9092 --earliest \
        -k string -v protobuf \
        -t my-protobuf-topic \
        --protobuf descriptor=my-descriptor.desc \
        --protobuf value=mypackage.MyMessage \
        --protobuf value.framing=confluent
```

Use `--protobuf value.framing=apicurio` for Apicurio-produced Protobuf. It
removes both the registry ID envelope and Apicurio's message-type reference
before decoding with the local schema. See the
[Protocol Buffers documentation](https://protobuf.dev/programming-guides/techniques/#self-description)
for more about `FileDescriptorSet`.

### Decode with a Schema Registry

`registry` decodes with the schema the record's ID points to, using the
[Schema Registry](#schema-registry) connection, and selects framing from the
configured provider:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry url=http://my-schema-registry:8081
```

With Confluent Schema Registry, it detects Avro, JSON Schema, and Protobuf from
each record's schema ID. Protobuf messages, including referenced schemas,
resolve from the registry, so no local schema file is needed.

The consumer rejects serializer-only properties, such as artifact selection and
auto-registration; the producer accepts the ones in
[Produce with a Schema Registry](#produce-with-a-schema-registry).

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
fallback encoding separately from explicit BYTES fields:

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

Details, copy, export, and warning tooltips keep the diagnostic while the
other field stays decoded normally.

### Record Details, copy, and export

The records table's Size column shows each record's total raw size. Press
`Enter` on a record to open Record Details, which puts the key, value, ordered
headers, and complete record JSON (Export) in tabs while keeping the total raw
size, partition, offset, and timestamp visible. The topic stays in the border
title.

- Key and value show compact deserializer, schema, and original payload-size
  diagnostics above their complete content. Explicit BYTES encoding appears
  beside the deserializer, and deserialization failures use a highlighted error
  panel that names the BYTES fallback encoding.
- The Headers tab shows zero-based indices in a compact table and reveals a
  full header name in a tooltip when it is truncated. The selected header shows
  its name and size, and All Headers shows every header together.
- A header's size counts its name and value, as Total Size does. Sizes appear in
  bytes below 1 KB, in KB below 1 MB, and in MB from there, with
  1 KB = 1,000 bytes.

Press `y` in the records table to copy the selected record as readable JSON.
In Record Details, `y` copies only the content of the key, the value, or the
selected header: strings, including BYTES fallback text, as plain text, and
other content as readable JSON. Null content copies nothing. On the Export tab,
`y` copies the complete record JSON. [Clipboard](#clipboard) explains how
copying reaches your system clipboard.

Press `Ctrl+E` in the records table or any Record Details tab to export the
complete record JSON. Local terminals save to Downloads; web-hosted sessions use
a browser download.

The Export tab, copied records, and exported files share the contract in
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
the Registry can resolve them unambiguously. Headers stay ordered, timestamps
use UTC ISO 8601 milliseconds, and tombstones use `content: null`. Enter lowercase
`null` in a key, value, or header filter to match null content.

### Consumer configuration

Kaskade honors `group.id` from Kafka client configuration. When it is omitted,
Kaskade creates an ephemeral `kaskade-<uuid>` group. Set `group.id` explicitly
when the Kafka principal is restricted to a specific consumer group.
`--earliest` and explicit `--partition` reads use direct partition assignment;
they do not use committed offsets.

The consumer's poll, idle, assignment, and request deadlines are in
[Operation timeouts](#operation-timeouts).

### Consumer shortcuts

These add to the [shortcuts every mode shares](#keyboard-shortcuts). The
binding ID is the name to use in a [custom keymap](#custom-keymap).

| Action | Shortcut | Binding ID |
| --- | --- | --- |
| Open Record Details | `Enter` | `kaskade.records.show` |
| Filter records | `/` or `Ctrl+F` | `kaskade.records.filter` |
| Show all records after filtering | `Esc` | `kaskade.records.show-all` |
| Consume more records | `n` | `kaskade.records.consume` |
| Change record chunk size | `#` | `kaskade.records.chunk-size` |
| Copy the selected record | `y` | `kaskade.records.copy` |
| Export the selected record | `Ctrl+E` | `kaskade.records.export` |
| Previous or next record in Record Details | `N`/`p` or `n` | `kaskade.record-details.previous`, `kaskade.record-details.next` |
| Apply record filters or select a chunk size | `Enter` | `kaskade.filter-records.apply`, `kaskade.chunk-size.select` |

## Producer

### Compose and produce

`kaskade producer` composes and produces one record at a time to the topic given
with `-t`:

```bash
kaskade producer -b my-kafka:9092 -t orders
kaskade producer -b my-kafka:9092 -t orders -k string -v json --partition 2
```

The composer has three tabs, Key, Value, and Headers, and a Summary panel
beside them.

- Key and Value each have a Null control and a content editor. The frame's
  subtitle shows the open field's size, such as `Value: 16 bytes`, or what
  makes it invalid. Empty content and null are different: an empty string is
  valid Kafka data, while a null value can act as a tombstone on compacted
  topics.
- Headers is an editable table of names and values. There is always an empty
  row at the bottom; typing in it adds a header. Check Null to send a null
  value, and press `Ctrl+D` to remove the focused header. Order, duplicate
  names, and empty values are kept; every header needs a name.
- Summary shows whether the record is ready, plus the topic, partition,
  serializers, serialized sizes, the header count and size, and the client's
  acks, idempotence, and compression. A `registry` field also shows its
  subject or artifact, version, and schema ID. Total Size adds the Key, Value,
  and headers, as the consumer's Total Size does. Sizes appear in bytes, KB, or
  MB. Press `F3` to hide or show it; it starts hidden on terminals narrower
  than 80 columns.

A record must fit two limits: the client's `message.max.bytes`, 1,000,000 bytes
by default, and the topic's `max.message.bytes`, which the cluster sets. Kaskade
can't read the topic limit without extra permissions, so it doesn't check it in
advance; a record over either limit fails with `Record Too Large`, naming which
one.

Press `Ctrl+S` to produce. Kaskade validates and serializes the Key and Value,
then waits for the broker. It reports success only after the broker acknowledges
the record, with its partition, offset, and timestamp:

```text
Delivered · Partition 2 · Offset 8429 · 14:20:05.120
```

Produce is disabled while a delivery is in progress. The draft stays after both
success and failure, so you can change it and produce again. Failures say
whether serialization, authorization, a timeout, or the broker caused them.
Kaskade never logs record content.

### Serializers

Choose the Key and Value serializers with `-k` and `-v`; both default to
`string`. They stay fixed while the producer runs.

| Serializer | Content |
| --- | --- |
| `string` | UTF-8 text |
| `bytes` | Text in the `--bytes` encoding: `base64` (default), `hex`, `byte-array` (a JSON array of 0–255), or `escaped` |
| `boolean` | `true` or `false` |
| `integer`, `long` | Big-endian 32-bit or 64-bit signed integers |
| `float`, `double` | Big-endian 32-bit or 64-bit IEEE 754 numbers |
| `json` | Any JSON document, sent compact; `--json` adds a JSON Schema |
| `avro` | JSON, encoded as Avro binary with an `--avro` schema file |
| `protobuf` | JSON, encoded as a Protobuf message from a `--protobuf` schema |
| `registry` | JSON, encoded with the schema registered for the topic |

`--bytes` accepts `encoding`, `key.encoding`, and `value.encoding`, like the
consumer's [byte presentation](#byte-presentation):

```bash
kaskade producer -b my-kafka:9092 -t orders -k bytes -v bytes --bytes key.encoding=hex
```

For `avro`, `protobuf`, and `registry`, compose the JSON the consumer shows for
the same record. A Key or Value copied from the consumer produces the same
bytes again, including Avro timestamps, dates, decimals, and nested bytes in
the form the consumer displays them (`2026-10-08 14:20:05.120000+00:00`,
`b'\x00'`).

When the content is JSON, the editor highlights it in the consumer's colors:
for `json`, `avro`, `protobuf`, `registry`, `boolean`, the number serializers,
and `bytes` with `byte-array`. `string` and the other `bytes` encodings stay
plain text.

Validation errors appear in the frame's subtitle and the Summary. They name
the field path and the rule, such as `$.age fails minimum 0` or
`Doesn't match the Avro schema at User.age: expected int`, and never repeat
the content.

### Produce with schema files

Local schema files encode records without a registry. Kaskade reads them
before the composer opens, so an unreadable or invalid file fails right away,
naming the option.

```bash
kaskade producer -b my-kafka:9092 -t users -v json --json value=user.json
kaskade producer -b my-kafka:9092 -t users -v avro --avro value=user.avsc
kaskade producer -b my-kafka:9092 -t users -v protobuf \
        --protobuf descriptor=my-descriptor.desc \
        --protobuf value=mypackage.User
```

- `--json key=…` and `value=…` validate the JSON before it is produced. Each
  `$ref` resolves against files next to the schema; remote URLs are never
  fetched. Without a schema, `json` sends any valid JSON.
- `--avro key=…` and `value=…` take `.avsc` files. They are required for each
  field that uses `avro`.
- `--protobuf` takes the schema and message names as in the consumer's
  [Protobuf](#protobuf) section: `descriptor=…` or `source=…` with optional
  `include=…`, and `key=…` or `value=…`.

These serializers write the raw encoding without Confluent or Apicurio
framing: the five-byte header needs a schema ID that only a registry can
confirm. Use [`registry`](#produce-with-a-schema-registry) for framed records.

### Produce with a Schema Registry

`registry` looks up the schema registered for the topic, encodes the record
with it, and writes the five-byte header with its ID. It uses the same
[Schema Registry](#schema-registry) connection as the consumer:

```bash
kaskade producer -b my-kafka:9092 -t users -v registry \
        --registry url=http://my-schema-registry:8081
kaskade producer -b my-kafka:9092 -t users -v registry \
        --registry provider=apicurio \
        --registry apicurio.registry.url=http://my-apicurio-registry:8080/apis/registry/v3
```

Kaskade chooses the schema the way the official serializers do:

| Provider | Default schema | Choose another |
| --- | --- | --- |
| Confluent | Latest version of subject `<topic>-key` or `<topic>-value` | `use.schema.id=<id>` |
| Apicurio | Latest version of artifact `<topic>-key` or `<topic>-value` in group `default` | `apicurio.registry.artifact.group-id`, `apicurio.registry.artifact.artifact-id`, `apicurio.registry.artifact.version` |

Each selection property applies to both fields, or to one with a `key.` or
`value.` prefix, such as `--registry value.use.schema.id=12`. Confluent's
`use.latest.version=true` and Apicurio's `apicurio.registry.find-latest=true`
are accepted. `false` needs a schema to [register](#register-schemas), or an
Apicurio version.

The framing follows the schema type:

| Schema | After the header |
| --- | --- |
| JSON Schema | The validated JSON, compact |
| Avro | Avro binary |
| Protobuf, Confluent | Message indexes, then the Protobuf binary |
| Protobuf, Apicurio | A message-type reference, then the Protobuf binary |

Protobuf uses the first message in the schema. Choose another with
`--registry protobuf.message=Order` or a nested name such as `Order.Line`.
Imported schemas resolve from the registry.

The lookup runs when the composer opens. Until it finishes, the field shows
`Looking up the schema`. If it fails, for example because the subject doesn't
exist, the field shows the registry's error, and `Ctrl+S` looks up the schema
again before producing.

### Register schemas

Kaskade registers a schema only when you enable auto-registration, which is off
by default, and give the field a local schema file:

```bash
kaskade producer -b my-kafka:9092 -t users -v registry \
        --registry url=http://my-schema-registry:8081 \
        --registry auto.register.schemas=true \
        --avro value=user.avsc
kaskade producer -b my-kafka:9092 -t users -v registry \
        --registry provider=apicurio \
        --registry apicurio.registry.url=http://my-apicurio-registry:8080/apis/registry/v3 \
        --registry apicurio.registry.auto-register=true \
        --protobuf source=user.proto --protobuf value=mypackage.User
```

The field takes exactly one schema file: `--avro`, `--json`, or `--protobuf`
with its message name. Kaskade registers it under the subject or artifact from
[Produce with a Schema Registry](#produce-with-a-schema-registry), when the
composer opens, and frames each record with the returned ID. Registering the
same content again returns the existing version, so producing twice keeps one
version. Confluent's `normalize.schemas=true` normalizes the schema before
registering it.

The schema's references are registered first, each under its own reference
name in the same registry and group:

| Schema | Reference | Subject or artifact |
| --- | --- | --- |
| Avro | A named type the file doesn't define, read from `<full name>.avsc` next to it | `shop.Address` |
| JSON Schema | A relative `$ref` file | `defs/address.json` |
| Protobuf | An `import`; bundled well-known types such as `google/protobuf/timestamp.proto` are never registered | `common/address.proto` |

Confluent stores Protobuf as compiled descriptors, as its own serializer does,
so either `descriptor=` or `source=` works. Apicurio stores `.proto` text and
needs `source=`.

As in the official serializers, registration can't be combined with
`use.latest.version=true`, `use.schema.id`, `apicurio.registry.find-latest=true`,
or `apicurio.registry.artifact.version`. Registration needs write access to the
registry. A compatibility rule or read-only credentials make the field show the
registry's error.

### Load a draft from a file

`--source` loads a record draft from a JSON file into the composer instead of
starting empty:

```json
{"headers": [{"key": "trace", "value": "abc"}, {"key": "trace", "value": null}], "key": {"content": "order-42"}, "value": {"content": {"status": "paid"}}}
```

A missing `key` or `value`, or `"content": null`, is null. The draft is
produced only when you press `Ctrl+S`, and the file is never modified.

### Producer configuration

These options set common producer properties:

| Option | Kafka property | Default when unset |
| --- | --- | --- |
| `--acks all\|-1\|0\|1` | `acks` | `all` |
| `--compression none\|gzip\|snappy\|lz4\|zstd` | `compression.type` | `none` |
| `--idempotence true\|false` | `enable.idempotence` | `false` |

The defaults are `confluent-kafka`'s. Unlike Kafka's Java client, it doesn't
enable idempotence by default.

The same properties can live in the `[kafka]` section of `--config-file` or in
`--kafka`. The options above apply only when you pass them, above `--kafka` and
below `-b`, as [Configuration precedence](#configuration-precedence) lists, so
an option you don't pass never replaces a configured or default value.

`confluent-kafka` checks that the settings are compatible. For example,
`--idempotence true --acks 1` fails before the composer opens with a message that
`acks` must be `all`.

The delivery and flush deadlines are in [Operation timeouts](#operation-timeouts).
When Kaskade closes, it flushes queued records for up to `producer.flush`
seconds.

### Producer shortcuts

These add to the [shortcuts every mode shares](#keyboard-shortcuts). The
binding ID is the name to use in a [custom keymap](#custom-keymap).

| Action | Shortcut | Binding ID |
| --- | --- | --- |
| Produce the composed record | `Ctrl+S`, `Ctrl+Shift+S`, or `F2` | `kaskade.compose.produce` |
| Show or hide the Summary | `F3` | `kaskade.compose.summary` |
| Delete the focused header | `Ctrl+D` | `kaskade.headers.delete` |

## Application settings

`settings.yaml` holds the settings that every mode shares. On Linux and macOS,
Kaskade reads `$XDG_CONFIG_HOME/kaskade/settings.yaml`. If `XDG_CONFIG_HOME` is
not set, it reads `~/.config/kaskade/settings.yaml`. Set `KASKADE_SETTINGS` to
use a different file.

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

### Custom themes

Define themes under `themes` in `settings.yaml`, then select one by name with
`theme`, `--theme`, or the Commands window:

```yaml
theme: solarized-kaskade

themes:
  solarized-kaskade:
    primary: "#268BD2"
    secondary: "#2AA198"
    warning: "#B58900"
    error: "#DC322F"
    success: "#859900"
    accent: "#6C71C4"
    foreground: "#839496"
    background: "#002B36"
    surface: "#073642"
    panel: "#002B36"
    boost: "#0A4050"
    dark: true
```

Only `primary` is required. Omitted properties fall back as follows:

| Property | When omitted |
| --- | --- |
| `secondary`, `warning`, `accent` | `primary` |
| `error`, `success` | `secondary` |
| `background`, `surface` | Textual's dark or light default |
| `foreground` | A contrasting color for `background` |
| `panel`, `boost` | Derived from `surface` and `primary` |
| `dark` | `true`; set `false` for a light theme |

Colors are opaque hex values, `rgb()` or `hsl()` values, CSS color names, or
Textual ANSI colors such as `ansi_blue`, which follow the terminal palette.
Quote hex colors, because YAML reads an unquoted `#` as a comment.

Theme names use lowercase letters, digits, and single hyphens. A custom theme
never replaces a Textual or Kaskade theme: a definition that reuses one of those
names is ignored, and the built-in theme stays available. Kaskade warns about
invalid names and properties at startup, ignores those properties, and keeps
the rest. A theme without a valid `primary` is ignored; selecting it falls back
to `eva01-berserk`.

### Operation timeouts

Operation timeouts are Kaskade deadlines in seconds, not `confluent-kafka`
properties. Configure them per command in `settings.yaml`:

```yaml
admin:
  timeouts:
    read: 10
    write: 60

consumer:
  timeouts:
    poll: 0.5
    idle: 2.5
    assignment: 15
    request: 10

producer:
  timeouts:
    delivery: 45
    flush: 5
```

Values support decimals and must be greater than zero; missing or invalid values
use the default, with an in-app warning when invalid. Override them for one
session with the repeatable `--timeout property=seconds` option. Each command
accepts only its own properties:

```bash
kaskade admin -b my-kafka:9092 \
    --timeout admin.read=20 \
    --timeout admin.write=90

kaskade consumer -b my-kafka:9092 -t my-topic \
    --timeout consumer.request=20 \
    --timeout consumer.assignment=30

kaskade producer -b my-kafka:9092 -t my-topic \
    --timeout producer.delivery=60
```

| `settings.yaml` | `--timeout` | Command | Default | Operation |
| --- | --- | --- | ---: | --- |
| `admin.timeouts.read` | `admin.read` | admin | 10 | Topic metadata, offsets, configurations, and consumer groups |
| `admin.timeouts.write` | `admin.write` | admin | 60 | Create, edit, delete, and partition-change operations |
| `consumer.timeouts.poll` | `consumer.poll` | consumer | 0.5 | Each consumer fetch poll |
| `consumer.timeouts.idle` | `consumer.idle` | consumer | 2.5 | Stop a page load after consecutive empty polls |
| `consumer.timeouts.assignment` | `consumer.assignment` | consumer | 15 | Wait for initial assignment or rebalance |
| `consumer.timeouts.request` | `consumer.request` | consumer | 10 | Consumer topic metadata and watermark requests |
| `producer.timeouts.delivery` | `producer.delivery` | producer | 45 | Wait for the broker acknowledgement of one record; keep it above the client's 30-second wait for a missing topic |
| `producer.timeouts.flush` | `producer.flush` | producer | 5 | Flush queued records when Kaskade closes |

Precedence, from lowest to highest, is the defaults, `settings.yaml`, then
`--timeout`. Native `confluent-kafka` properties such as `socket.timeout.ms`,
`socket.connection.setup.timeout.ms`, and `session.timeout.ms` belong in
`[kafka]` or repeated `--kafka` options.

### Keyboard shortcuts

Kaskade supports arrow keys and Vim-style navigation. Where k9s has the same
action, Kaskade uses the same key. These shortcuts work in every mode; the
[Admin](#admin-shortcuts), [Consumer](#consumer-shortcuts), and
[Producer](#producer-shortcuts) sections list the rest.

| Action | Shortcut | Binding ID |
| --- | --- | --- |
| Move | `h`, `j`, `k`, `l` or arrow keys | `kaskade.navigation.left`, `.down`, `.up`, `.right` |
| First or last item | `g` or `G` | `kaskade.navigation.first`, `.last` |
| Page up or down | `PageUp` or `PageDown` | `kaskade.navigation.page-up`, `.page-down` |
| Select or apply a modal action | `Enter` | `kaskade.navigation.select` |
| Back or clear a filter | `Esc` | |
| Help | `?` or `F1` | `help.toggle` |
| Commands | `:` or `Ctrl+P` | `app.command-palette` |
| Quit | `Ctrl+C` | `app.quit` |
| Copy selected screen text | `Cmd+C` on macOS or `Ctrl+Shift+C` on Linux | |

Help lists every contextual shortcut alias. Navigate with the standard keys and
close with `Esc`, `q`, `?`, or `F1`. The Commands palette links to the same Help.

Plain-character shortcuts don't intercept typing in filter and editor fields,
and `Enter` keeps its normal submission or selection behavior within form
controls.

Terminals without distinct shifted-control key encoding may treat
`Ctrl+Shift+S` as `Ctrl+S`; both bindings save and produce.

Zellij uses `Ctrl+S` and `Ctrl+P` in its default keymap. Inside Zellij, use
`F2` to save or produce, and `:` to open Commands when no text field has focus,
or lock Zellij with `Ctrl+G` first. tmux only reserves its `Ctrl+B` prefix,
which Kaskade doesn't use.

### Custom keymap

Rebind shortcuts under `keymap` in `settings.yaml`, using the binding IDs from
the shortcut tables and Textual key names. Separate keys with commas to assign
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

These binding IDs aren't in the shortcut tables:

| Context | Binding IDs |
| --- | --- |
| Navigation | `kaskade.navigation.home`, `.end`, `.page-left`, `.page-right` |
| Back and cancel | `kaskade.help.close`, `kaskade.describe-topic.close`, `kaskade.filter-topics.close`, `kaskade.create-topic.close`, `kaskade.edit-topic.close`, `kaskade.delete-topic.cancel`, `kaskade.record-details.close`, `kaskade.filter-records.close`, `kaskade.chunk-size.close` |

Unknown binding IDs, invalid key names, and malformed configuration produce an
in-app warning while Kaskade continues with its default bindings.

### Clipboard

`y` copies the selected topic name in Admin, also from Topic Details, and the
selected record in Consumer, as
[Record Details, copy, and export](#record-details-copy-and-export) describes.
Copy and Export Record appear in Help and Commands, not in the Footer.

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
computer, so it can work when Kaskade runs through SSH or `kubectl exec -it`;
the remote machine or pod does not need its own clipboard. Every intermediate
layer must preserve the escape sequence. Terminal multiplexers such as tmux may
require
[additional clipboard configuration](https://github.com/tmux/tmux/wiki/Clipboard#quick-summary),
and browser terminals or other relays may filter OSC 52.

### Kantrip profile

When `KANTRIP_PROFILE` is set to a non-empty value, as
[`kantrip exec`](https://github.com/sauljabin/kantrip/blob/main/USAGE.md#application-environment-from-kantrip-exec)
does, every mode shows it before the bootstrap server in the header, as
`staging · kafka:9092`. The name is display-only: it does not change the
connection, and Kaskade reads no other `KANTRIP_*` variable.

### Logs

Kaskade writes logs to `$XDG_STATE_HOME/kaskade/kaskade.log`. If
`XDG_STATE_HOME` is not set, it writes to
`~/.local/state/kaskade/kaskade.log`.

The active log rotates at 5 MiB, and Kaskade keeps three backups named
`kaskade.log.1` through `kaskade.log.3`, so logs use about 20 MiB at most.

## Agent skill and cheatsheet

The [agentskills](https://github.com/sauljabin/agentskills) repository has a
`kaskade` skill that teaches coding agents such as Claude Code, Codex, or Cursor
to use Kaskade. Install it with the [skills](https://www.skills.sh/) CLI:

```bash
skills add sauljabin/agentskills --skill kaskade
```

The [cheatsheets](https://github.com/sauljabin/cheatsheets) repository has a
`kaskade` sheet with common commands for the [cheat](https://github.com/cheat/cheat)
CLI. After installing the cheatsheets as their README describes, run
`cheat kaskade`.
