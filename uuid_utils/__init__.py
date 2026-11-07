"""Stub implementation of uuid_utils used by langchain_core.
Provides a minimal ``uuid7`` function returning a UUID4 string (good enough for tests)."""
import uuid

def uuid7():
    return uuid.uuid4()
