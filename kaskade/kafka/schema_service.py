from confluent_kafka.avro import CachedSchemaRegistryClient

from kaskade.config import Config
from kaskade.kafka.mappers import metadata_to_schema
from kaskade.kafka.models import Schema


class SchemaService:
    def __init__(self, config: Config):
        self.config = config
        self.schema_registry_config = self.config.schema_registry.copy()
        self.schema_registry_client = CachedSchemaRegistryClient(
            self.schema_registry_config
        )

    def get_by_id(self, id: int) -> Schema:
        return metadata_to_schema(self.schema_registry_client.get_by_id(id))


if __name__ == "__main__":
    from rich import print

    config = Config("kaskade.yml")
    client = SchemaService(config)
    schema = client.get_by_id(1)
    print(schema)
    print(schema.type)
    print(schema.json)
