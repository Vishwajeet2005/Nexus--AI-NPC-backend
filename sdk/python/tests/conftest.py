import pytest_asyncio
from nexus_py import NexusClient

@pytest_asyncio.fixture
async def client() -> NexusClient:
    async with NexusClient(host="test.nexus.local:8000") as c:
        yield c
