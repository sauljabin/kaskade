"""Schema loading and Registry schema resolution.

The consumer deserializers and the producer serializers share this package, so
both directions read local files and Registry schemas, with their references,
the same way. Encoding and decoding stay in their own packages.
"""

from kaskade.schemas.errors import SchemaError

__all__ = ["SchemaError"]
