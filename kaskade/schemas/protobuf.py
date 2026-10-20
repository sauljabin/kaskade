"""Protobuf descriptors from descriptor sets, Registry descriptors, or `.proto` sources."""

import tempfile
from collections.abc import Mapping
from functools import cache
from pathlib import Path

import grpc_tools  # type: ignore[import-untyped]
from google.protobuf.descriptor import Descriptor
from google.protobuf.descriptor_pb2 import FileDescriptorProto, FileDescriptorSet
from google.protobuf.descriptor_pool import Default as DefaultDescriptorPool
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import DecodeError, Message
from google.protobuf.message_factory import GetMessages
from grpc_tools import protoc

from kaskade.files import file_to_bytes
from kaskade.schemas.errors import SchemaError

ROOT_PROTO = "root.proto"


def descriptor_pool(
    root: FileDescriptorProto, descriptors: dict[str, FileDescriptorProto]
) -> DescriptorPool:
    """Build a pool from `root` and its dependencies.

    Dependencies missing from `descriptors` come from the well-known types bundled
    with protobuf.
    """
    pool = DescriptorPool()
    _add_descriptor(root, descriptors, pool, set(), set())
    return pool


def _add_descriptor(
    descriptor: FileDescriptorProto,
    descriptors: dict[str, FileDescriptorProto],
    pool: DescriptorPool,
    added: set[str],
    visiting: set[str],
) -> None:
    if descriptor.name in added:
        return
    if descriptor.name in visiting:
        raise SchemaError("Cyclic Protobuf schema reference")

    visiting.add(descriptor.name)
    for dependency in descriptor.dependency:
        referenced = descriptors.get(dependency)
        if referenced is not None:
            _add_descriptor(referenced, descriptors, pool, added, visiting)
        else:
            _add_default_descriptor(dependency, pool, added)
    try:
        pool.Add(descriptor)
    except (TypeError, ValueError) as ex:
        raise SchemaError(f"Invalid Protobuf descriptor: {descriptor.name}") from ex
    visiting.remove(descriptor.name)
    added.add(descriptor.name)


def _add_default_descriptor(name: str, pool: DescriptorPool, added: set[str]) -> None:
    if name in added:
        return
    try:
        descriptor = DefaultDescriptorPool().FindFileByName(name)
    except KeyError as ex:
        raise SchemaError(f"Protobuf schema reference not found: {name}") from ex
    for dependency in descriptor.dependencies:
        _add_default_descriptor(dependency.name, pool, added)
    pool.AddSerializedFile(descriptor.serialized_pb)
    added.add(name)


def compile_sources(sources: dict[str, str]) -> tuple[FileDescriptorProto, DescriptorPool]:
    """Compile `.proto` sources, whose root is `root.proto`, into its descriptor and pool."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, content in sources.items():
            path = _safe_proto_path(root, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        descriptor_path = root / "schema.desc"
        result = protoc.main(
            [
                "grpc_tools.protoc",
                f"-I{root}",
                f"-I{_bundled_protos()}",
                f"--descriptor_set_out={descriptor_path}",
                "--include_imports",
                ROOT_PROTO,
            ]
        )
        if result != 0:
            raise SchemaError("Invalid Protobuf schema")
        compiled = FileDescriptorSet.FromString(descriptor_path.read_bytes())
    descriptors = {descriptor.name: descriptor for descriptor in compiled.file}
    root_descriptor = descriptors.get(ROOT_PROTO)
    if root_descriptor is None:
        raise SchemaError("Compiled Protobuf root descriptor not found")
    return root_descriptor, descriptor_pool(root_descriptor, descriptors)


def _safe_proto_path(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise SchemaError(f"Unsafe Protobuf reference name: {name}")
    return root / relative


def find_message(pool: DescriptorPool, root: FileDescriptorProto, name: str) -> Descriptor:
    """Find a message by its full name, or by its name within the root's package."""
    try:
        return pool.FindMessageTypeByName(name)
    except KeyError:
        qualified_name = ".".join(filter(None, (root.package, name)))
        try:
            return pool.FindMessageTypeByName(qualified_name)
        except KeyError as ex:
            raise SchemaError(f"Protobuf message not found: {name}") from ex


def first_message(pool: DescriptorPool, root: FileDescriptorProto) -> Descriptor:
    """The first message the root file declares, as the official serializers default to."""
    if not root.message_type:
        raise SchemaError("Protobuf schema contains no messages")
    return find_message(pool, root, root.message_type[0].name)


BUILTIN_PREFIX = "google/protobuf/"


def is_builtin(name: str) -> bool:
    """Well-known types bundled with protobuf, which are never registered."""
    return name.startswith(BUILTIN_PREFIX)


def _bundled_protos() -> Path:
    return Path(grpc_tools.__file__).parent / "_proto"


def compile_proto_file(path: str | Path) -> FileDescriptorSet:
    """Compile a `.proto` file; its imports resolve from its directory or bundled types."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise SchemaError(f"Unable to read {path}")
    return FileDescriptorSet.FromString(_compiled(str(source)))


@cache
def _compiled(source: str) -> bytes:
    """Compile each source once per process, so protoc never runs again inside the TUI."""
    path = Path(source)
    with tempfile.TemporaryDirectory() as directory:
        descriptor_path = Path(directory) / "schema.desc"
        result = protoc.main(
            [
                "grpc_tools.protoc",
                f"-I{path.parent}",
                f"-I{_bundled_protos()}",
                f"--descriptor_set_out={descriptor_path}",
                "--include_imports",
                path.name,
            ]
        )
        if result != 0:
            raise SchemaError(f"Invalid Protobuf schema in {source}")
        return descriptor_path.read_bytes()


def load_descriptor_set(path: str | Path) -> FileDescriptorSet:
    try:
        return FileDescriptorSet.FromString(file_to_bytes(str(Path(path).expanduser())))
    except OSError as ex:
        raise SchemaError(f"Unable to read {path}: {ex}") from ex
    except (DecodeError, TypeError, ValueError) as ex:
        raise SchemaError(f"Invalid Protobuf descriptor set in {path}") from ex


def protobuf_descriptor_set(config: Mapping[str, str]) -> FileDescriptorSet:
    """The descriptor set from `descriptor=`, or compiled from `source=`."""
    if "source" in config:
        return compile_proto_file(config["source"])
    return load_descriptor_set(config["descriptor"])


def load_message_classes(config: Mapping[str, str]) -> dict[str, type[Message]]:
    """Message classes by full name, from a descriptor set or a `.proto` source."""
    descriptor_set = protobuf_descriptor_set(config)
    try:
        return GetMessages(descriptor_set.file)
    except (KeyError, TypeError, ValueError) as ex:
        raise SchemaError("Invalid Protobuf descriptors") from ex
