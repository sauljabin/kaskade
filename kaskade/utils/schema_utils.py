import struct
from io import BytesIO
from typing import Any

from avro.io import BinaryDecoder, DatumReader
from avro.schema import parse

from kaskade.kafka.models import Schema

MAGIC_BYTES = 0


def unpack_schema_id(binary: bytes) -> int:
    magic, schema_id = struct.unpack(">bI", binary[:5])
    if magic == MAGIC_BYTES:
        return int(schema_id)
    else:
        return -1


def deserialize_avro(schema: Schema, binary: bytes) -> Any:
    schema = parse(schema.json_file)
    output = BinaryDecoder(BytesIO(binary[5:]))
    reader = DatumReader(schema)
    return reader.read(output)
