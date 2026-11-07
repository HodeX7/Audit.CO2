def uuid7():
    """Return a UUIDv7‑like value. For the test suite we can just return a UUID4 string.
    This mirrors the API of the real ``uuid_utils.compat`` module.
    """
    import uuid
    return uuid.uuid4()

