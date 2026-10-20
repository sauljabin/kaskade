"""Local schemas prepared for registration, with the documents they reference.

A registry stores each referenced document under its own subject or artifact,
named after the reference: the Avro full name, the `$ref` path, or the Protobuf
import path. That is the name Confluent's own serializers use by default.
"""

import json
from base64 import b64encode
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastavro import parse_schema
from fastavro.schema import UnknownType
from google.protobuf.descriptor_pb2 import FileDescriptorProto
from google.protobuf.message_factory import GetMessages

from kaskade.configs import SchemaType
from kaskade.schemas.avro import AVRO_SCHEMA_EXCEPTIONS
from kaskade.schemas.errors import SchemaError
from kaskade.schemas.json_schema import (
    json_validator,
    local_reference_path,
    local_references,
    read_json_text,
)
from kaskade.schemas.protobuf import is_builtin, protobuf_descriptor_set


@dataclass(frozen=True)
class DocumentReference:
    name: str
    document: "SchemaDocument"


@dataclass(frozen=True)
class SchemaDocument:
    """A schema's content as the registry stores it, with its direct references."""

    type: SchemaType
    content: str
    references: tuple[DocumentReference, ...] = ()


def avro_document(path: str | Path) -> SchemaDocument:
    """An .avsc file; named types it doesn't define come from `<full name>.avsc` next to it."""
    schema_path = Path(path).expanduser()
    document, _ = _avro_document(schema_path, schema_path.resolve().parent, {}, ())
    return document


def _avro_document(
    path: Path,
    directory: Path,
    loaded: dict[str, tuple[SchemaDocument, dict[str, Any]]],
    visiting: tuple[str, ...],
) -> tuple[SchemaDocument, dict[str, Any]]:
    text, schema = read_json_text(path)
    known: dict[str, Any] = {}
    references: list[DocumentReference] = []
    while True:
        named = dict(known)
        try:
            parse_schema(schema, named_schemas=named)
        except UnknownType as ex:
            name = ex.name
            if name in visiting:
                raise SchemaError(f"Avro types {name} and {path.name} reference each other") from ex
            if name not in loaded:
                dependency = directory / f"{name}.avsc"
                if not dependency.is_file():
                    raise SchemaError(
                        f"Avro type {name} isn't defined; expected {dependency.name} "
                        "next to the schema"
                    ) from ex
                loaded[name] = _avro_document(dependency, directory, loaded, (*visiting, name))
            dependency_document, dependency_named = loaded[name]
            known.update(dependency_named)
            references.append(DocumentReference(name, dependency_document))
        except AVRO_SCHEMA_EXCEPTIONS as ex:
            raise SchemaError(f"Invalid Avro schema in {path}: {ex}") from ex
        else:
            return SchemaDocument(SchemaType.AVRO, text, tuple(references)), named


def json_document(path: str | Path) -> SchemaDocument:
    """A JSON Schema file; each relative `$ref` file becomes a reference by its path."""
    schema_path = Path(path).expanduser()
    return _json_document(schema_path, schema_path.resolve().parent, "", {}, ())


def _json_document(
    path: Path,
    directory: Path,
    uri: str,
    loaded: dict[str, SchemaDocument],
    visiting: tuple[str, ...],
) -> SchemaDocument:
    text, schema = read_json_text(path)
    references: list[DocumentReference] = []
    for reference in local_references(schema, uri):
        if reference in visiting or reference == uri:
            raise SchemaError(f"JSON Schema references {reference} and {path.name} form a cycle")
        if reference not in loaded:
            loaded[reference] = _json_document(
                local_reference_path(directory, reference),
                directory,
                reference,
                loaded,
                (*visiting, uri),
            )
        references.append(DocumentReference(reference, loaded[reference]))
    if not uri:
        # Check the schema the same way validation does before registering it.
        json_validator(json.loads(text), {})
    return SchemaDocument(SchemaType.JSON, text, tuple(references))


def protobuf_document(
    config: Mapping[str, str], message_name: str, *, as_source: bool
) -> SchemaDocument:
    """The file that declares `message_name`, with its imports as references.

    Confluent stores serialized descriptors, as its serializer registers them;
    Apicurio stores `.proto` text, so `as_source` needs a `source=` file. Bundled
    well-known types are never registered.
    """
    descriptor_set = protobuf_descriptor_set(config)
    files = {descriptor.name: descriptor for descriptor in descriptor_set.file}
    message_class = GetMessages(descriptor_set.file).get(message_name)
    if message_class is None:
        raise SchemaError(f"Protobuf message {message_name} isn't in the schema")
    source_directory: Path | None = None
    if as_source:
        if "source" not in config:
            raise SchemaError("Registering Protobuf in Apicurio needs --protobuf source=my.proto")
        source_directory = Path(config["source"]).expanduser().resolve().parent
    return _protobuf_document(message_class.DESCRIPTOR.file.name, files, source_directory, {})


def _protobuf_document(
    name: str,
    files: dict[str, FileDescriptorProto],
    source_directory: Path | None,
    loaded: dict[str, SchemaDocument],
) -> SchemaDocument:
    descriptor = files[name]
    references = []
    for dependency in descriptor.dependency:
        if is_builtin(dependency):
            continue
        if dependency not in loaded:
            loaded[dependency] = _protobuf_document(dependency, files, source_directory, loaded)
        references.append(DocumentReference(dependency, loaded[dependency]))
    if source_directory is None:
        content = b64encode(descriptor.SerializeToString()).decode("ascii")
    else:
        try:
            content = (source_directory / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as ex:
            raise SchemaError(f"Unable to read {name}: {ex}") from ex
    return SchemaDocument(SchemaType.PROTOBUF, content, tuple(references))
