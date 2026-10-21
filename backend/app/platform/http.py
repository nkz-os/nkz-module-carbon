"""HTTP helper: use the caller's client, or a short-lived one."""

import httpx


async def http_get(client: httpx.AsyncClient | None, url: str, **kwargs) -> httpx.Response:
    if client is not None:
        return await client.get(url, **kwargs)
    async with httpx.AsyncClient() as c:
        return await c.get(url, **kwargs)
