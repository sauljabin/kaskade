class SchemaError(ValueError):
    """Raised when a schema can't be read, parsed, or resolved.

    Messages describe the schema problem and never contain record content.
    """
