<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="kaskade" width="400" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/banner.png"></a>
</p>

<p align="center">
<a href="https://github.com/sauljabin/kaskade"><img alt="GitHub" src="https://img.shields.io/badge/github-blueviolet?logo=github&logoColor=white"></a>
<a href="https://github.com/sponsors/sauljabin"><img alt="donate" src="https://img.shields.io/badge/donate-EA4AAA?logo=github-sponsors&logoColor=white"></a>
<a href="https://libraries.io/pypi/kaskade"><img alt="Libraries.io dependency status for latest release" src="https://img.shields.io/librariesio/release/pypi/kaskade?logo=python&logoColor=white&label="></a>
<a href="https://github.com/sauljabin/kaskade/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/sauljabin/kaskade"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Pypi Version" src="https://img.shields.io/pypi/v/kaskade"></a>
<a href="https://formulae.brew.sh/formula/kaskade"><img alt="Homebrew Version" src="https://img.shields.io/homebrew/v/kaskade"></a>
<a href="https://hub.docker.com/r/sauljabin/kaskade/tags"><img alt="Docker Version" src="https://img.shields.io/docker/v/sauljabin/kaskade?label=dockerhub"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Platform" src="https://img.shields.io/badge/os-linux%20%7C%20macos-blue"></a>
<a href="https://pypi.org/project/kaskade"><img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/kaskade?label=python"></a>
</p>

## Kaskade

Kaskade is a text user interface (TUI) for Apache Kafka, built with [Textual](https://github.com/Textualize/textual)
by [Textualize](https://www.textualize.io/).

It includes features like:

### Admin

- List topics, partitions, groups and group members.
- Topic information like lag, replicas and records count.
- Create, edit and delete topics.
- Filter topics by name.

### Consumer

- Json, string, integer, long, float, boolean and double deserialization.
- Filter by key, value, header and/or partition.
- Schema Registry support for avro and json.
- Protobuf deserialization support without Schema Registry.
- Avro deserialization without Schema Registry.

## Limitations

Kaskade does not include:

- Schema Registry for protobuf.
- Runtime auto-refresh.

## Screenshots

<table>
  <tr>
    <td>
      <img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/admin.png">
    </td>
    <td>
      <img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/create-topic.png">
    </td>
  </tr>
  <tr>
    <td>
      <img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/consumer.png">
    </td>
    <td>
      <img alt="kaskade" src="https://raw.githubusercontent.com/sauljabin/kaskade/main/screenshots/record.png">
    </td>
  </tr>
</table>

## Installation

#### Install it with `brew`:

```bash
brew install kaskade
```

[brew installation](https://brew.sh/).

#### Install it with `pipx`:

```bash
pipx install kaskade
```

[pipx installation](https://pipx.pypa.io/stable/installation/).

## Running kaskade

#### Admin view:

```bash
kaskade admin -b my-kafka:9092
```

#### Consumer view:

```bash
kaskade consumer -b my-kafka:9092 -t my-topic
```

## Configuration examples

#### Multiple bootstrap servers:

```bash
kaskade admin -b my-kafka:9092,my-kafka:9093
```

#### Consume and deserialize:

```bash
kaskade consumer -b my-kafka:9092 -t my-json-topic -k json -v json
```

> Supported deserializers `[bytes, boolean, string, long, integer, double, float, json, avro, protobuf, registry]`

#### Consuming from the beginning:

```bash
kaskade consumer -b my-kafka:9092 -t my-topic --from-beginning
```

#### Schema registry simple connection deserializer:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry url=http://my-schema-registry:8081
```

> For more information about Schema Registry configurations go
> to: [Confluent Schema Registry client](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html#schemaregistry-client).

#### Apicurio registry:

```bash
kaskade consumer -b my-kafka:9092 -t my-avro-topic \
        -k registry -v registry \
        --registry url=http://my-apicurio-registry:8081/apis/ccompat/v7
```

> For more about apicurio go to: [Apicurio registry](https://github.com/apicurio/apicurio-registry).

#### SSL encryption example:

```bash
kaskade admin -b my-kafka:9092 -c security.protocol=SSL
```

> For more information about SSL encryption and SSL authentication go
> to: [Configure librdkafka client](https://github.com/edenhill/librdkafka/wiki/Using-SSL-with-librdkafka#configure-librdkafka-client).

#### Confluent cloud admin and consumer:

```bash
kaskade admin -b ${BOOTSTRAP_SERVERS} \
        -c security.protocol=SASL_SSL \
        -c sasl.mechanism=PLAIN \
        -c sasl.username=${CLUSTER_API_KEY} \
        -c sasl.password=${CLUSTER_API_SECRET}
```

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

> More about confluent cloud configuration
> at: [Kafka client quick start for Confluent Cloud](https://docs.confluent.io/cloud/current/client-apps/config-client.html).

#### Running with docker:

```bash
docker run --rm -it --network my-networtk sauljabin/kaskade:latest \
    admin -b my-kafka:9092
```

```bash
docker run --rm -it --network my-networtk sauljabin/kaskade:latest \
    consumer -b my-kafka:9092 -t my-topic
```

#### Avro consumer:

Consume using `my-schema.avsc` file:

```bash
kaskade consumer -b my-kafka:9092 --from-beginning \
        -k string -v avro \
        -t my-avro-topic \
        --avro value=my-schema.avsc
```

#### Protobuf consumer:

Install `protoc` command:

```bash
brew install protobuf
```

Generate a _Descriptor Set_ file from your `.proto` file:

```bash
protoc --include_imports \
       --descriptor_set_out=my-descriptor.desc \
       --proto_path=${PROTO_PATH} \
       ${PROTO_PATH}/my-proto.proto
```

Consume using `my-descriptor.desc` file:

```bash
kaskade consumer -b my-kafka:9092 --from-beginning \
        -k string -v protobuf \
        -t my-protobuf-topic \
        --protobuf descriptor=my-descriptor.desc \
        --protobuf value=mypackage.MyMessage
```

> More about protobuf and `FileDescriptorSet` at: [Protocol Buffers documentation](https://protobuf.dev/programming-guides/techniques/#self-description).

#### AWS IAM Authentication:

```bash
kaskade admin -b my-kafka:9092 \
        -c security.protocol=SASL_SSL \
        -c sasl.mechanism=OAUTHBEARER \
        -c aws.region=eu-west-1
```

```bash
kaskade consumer -b my-kafka:9092 --from-beginning \
        -t my-topic \
        -c security.protocol=SASL_SSL \
        -c sasl.mechanism=OAUTHBEARER \
        -c aws.region=eu-west-1
```

## Questions

For Q&A go to [GitHub Discussions](https://github.com/sauljabin/kaskade/discussions/categories/q-a).

## Development

For development instructions see [DEVELOPMENT.md](https://github.com/sauljabin/kaskade/blob/main/DEVELOPMENT.md).
