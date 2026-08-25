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
