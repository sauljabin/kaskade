import json
from io import BytesIO
from typing import Any

from confluent_kafka.serialization import MessageField
from fastavro import schemaless_reader
from google.protobuf.message_factory import GetMessageClass

from kaskade import logger
from kaskade.apicurio import ApicurioArtifact, ApicurioClient, ApicurioConfig
from kaskade.configs import SCHEMA_REGISTRY_HEADER_SIZE, SCHEMA_REGISTRY_MAGIC_BYTE, SchemaType
from kaskade.deserializers.base import (
    SCHEMA_METADATA_EXCEPTIONS,
    ApicurioRegistrySchema,
    DeserializationError,
    DeserializationResult,
    Deserializer,
    _deserialize_avro,
    _registry_header,
    _require_field,
)
from kaskade.deserializers.protobuf import parse_message, parse_type_ref
from kaskade.schemas.apicurio import ApicurioSchemas
from kaskade.schemas.json_schema import validation_error
from kaskade.schemas.protobuf import find_message, first_message


class ApicurioRegistryDeserializer(Deserializer):
    def __init__(self, config: ApicurioConfig):
        self.registry_client = ApicurioClient(config)
        self.schemas = ApicurioSchemas(self.registry_client)

    def close(self) -> None:
        self.registry_client.close()

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        _, artifact, payload = self._artifact(data, topic, context)
        return self._deserialize_content(artifact, payload)

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        topic, artifact, payload = self._artifact(data, topic, context)
        content = self._deserialize_content(artifact, payload)
        return DeserializationResult(content, self._resolve_schema(artifact, topic, context))

    def _artifact(
        self, data: bytes, topic: str | None, context: MessageField
    ) -> tuple[str, ApicurioArtifact, bytes]:
        topic = _require_field(topic, context)
        if len(data) <= SCHEMA_REGISTRY_HEADER_SIZE:
            raise DeserializationError(
                f"Expecting Apicurio data framing of length {SCHEMA_REGISTRY_HEADER_SIZE + 1} "
                f"bytes or more but total data size is {len(data)} bytes"
            )
        magic, artifact_id = _registry_header(data)
        if magic != SCHEMA_REGISTRY_MAGIC_BYTE:
            raise DeserializationError(f"Unexpected Apicurio magic byte: {magic}")
        artifact = self.registry_client.get_artifact(artifact_id)
        return topic, artifact, data[SCHEMA_REGISTRY_HEADER_SIZE:]

    def _deserialize_content(self, artifact: ApicurioArtifact, payload: bytes) -> Any:
        match artifact.type:
            case SchemaType.JSON:
                return self._deserialize_json(artifact, payload)
            case SchemaType.AVRO:
                schema = self.schemas.avro_schema(artifact)
                return _deserialize_avro(schemaless_reader, BytesIO(payload), schema, None)
            case SchemaType.PROTOBUF:
                return self._deserialize_protobuf(artifact, payload)
            case _:
                raise DeserializationError("Schema type not supported")

    def _deserialize_json(self, artifact: ApicurioArtifact, payload: bytes) -> Any:
        _, json_payload = parse_type_ref(payload)
        try:
            content = json.loads(json_payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            content = json.loads(payload)
        error = validation_error(self.schemas.json_validator(artifact), content)
        if error is not None:
            raise DeserializationError(error)
        return content

    def _deserialize_protobuf(self, artifact: ApicurioArtifact, payload: bytes) -> Any:
        descriptor, pool = self.schemas.protobuf_descriptors(artifact)
        message_name, message_payload = parse_type_ref(payload)
        if message_name is None:
            message_descriptor = first_message(pool, descriptor)
            message_payload = payload
        else:
            message_descriptor = find_message(pool, descriptor, message_name)
        return parse_message(GetMessageClass(message_descriptor), message_payload)

    def _resolve_schema(
        self,
        artifact: ApicurioArtifact,
        topic: str,
        context: MessageField,
    ) -> ApicurioRegistrySchema:
        result = ApicurioRegistrySchema(
            id=artifact.id,
            id_kind=artifact.id_kind,
            type=artifact.type,
        )
        try:
            registrations = self.registry_client.get_metadata(artifact.id)
            candidates = [
                value for value in registrations if value.get("artifactId") and value.get("version")
            ]
            conventional_artifact = f"{topic}-{context.name.lower()}"
            conventional = [
                value for value in candidates if value.get("artifactId") == conventional_artifact
            ]
            selected = conventional[0] if len(conventional) == 1 else None
            if selected is None and len(candidates) == 1:
                selected = candidates[0]
            if selected is not None:
                result = ApicurioRegistrySchema(
                    id=artifact.id,
                    id_kind=artifact.id_kind,
                    type=artifact.type,
                    group=str(selected.get("groupId") or "default"),
                    artifact=str(selected["artifactId"]),
                    version=str(selected["version"]),
                )
        except SCHEMA_METADATA_EXCEPTIONS as ex:
            logger.warning(
                "schema metadata lookup failed schema_id=%d topic=%s field=%s error=%s",
                artifact.id,
                topic,
                context.name,
                ex,
            )
        return result
