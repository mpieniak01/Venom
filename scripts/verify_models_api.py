import asyncio
import json

import httpx

from venom_core.utils.url_policy import build_http_url


async def check_models():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(build_http_url("localhost", 8000, "/api/v1/models"))
            if resp.status_code == 200:
                print(json.dumps(resp.json(), indent=2))
            else:
                print(f"Error: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Connection failed: {e}")


if __name__ == "__main__":
    asyncio.run(check_models())
