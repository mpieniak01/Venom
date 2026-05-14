#!/usr/bin/env python3
"""Smoke test for Multi-Runtime service.

Tests basic functionality:
- Health check
- Status endpoint
- Model info
- Simple text-to-text inference
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


# Configuration
SERVICE_HOST = "127.0.0.1"
SERVICE_PORT = 8014
BASE_URL = f"http://{SERVICE_HOST}:{SERVICE_PORT}"
TIMEOUT = 120.0  # 2 minutes for model loading
HEALTH_CHECK_TIMEOUT = 5.0


class MultiRuntimeSmokeTester:
    """Smoke tester for Multi-Runtime."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.health_check_timeout = HEALTH_CHECK_TIMEOUT
        self.results: Dict[str, Any] = {}

    async def run(self) -> int:
        """Run all smoke tests.

        Returns:
            0 if all tests pass, 1 otherwise
        """
        print("=" * 60)
        print("Multi-Runtime Service - Smoke Tests")
        print("=" * 60)
        print(f"Target: {self.base_url}\n")

        tests = [
            ("Health Check", self.test_health),
            ("Status Endpoint", self.test_status),
            ("Models List", self.test_models_list),
            ("Text Response", self.test_text_response),
            ("Math Question", self.test_math_question),
        ]

        passed = 0
        failed = 0

        for test_name, test_func in tests:
            try:
                print(f"\n[TEST] {test_name}...")
                result = await test_func()
                if result:
                    print("  ✓ PASS")
                    passed += 1
                else:
                    print("  ✗ FAIL")
                    failed += 1
            except Exception as e:
                print(f"  ✗ ERROR: {e}")
                failed += 1

        print("\n" + "=" * 60)
        print(f"Results: {passed} passed, {failed} failed")
        print("=" * 60)

        return 0 if failed == 0 else 1

    async def test_health(self) -> bool:
        """Test health endpoint."""
        async with httpx.AsyncClient(timeout=self.health_check_timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code != 200:
                    print(f"  Status code: {response.status_code}")
                    return False
                data = response.json()
                print(f"  Status: {data.get('status')}")
                print(f"  Message: {data.get('message')}")
                return data.get("status") in ("ok", "warming")
            except Exception as e:
                print(f"  Failed to reach service: {e}")
                return False

    async def test_status(self) -> bool:
        """Test status endpoint."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/status")
                if response.status_code != 200:
                    print(f"  Status code: {response.status_code}")
                    return False
                data = response.json()
                print(f"  Service: {data.get('service')}")
                print(f"  Status: {data.get('status')}")
                print(f"  Model loaded: {data.get('model_loaded')}")
                if data.get("model_info"):
                    print(f"  Model ID: {data['model_info'].get('model_id')}")
                return data.get("model_loaded") in (True, None)
            except Exception as e:
                print(f"  Error: {e}")
                return False

    async def test_models_list(self) -> bool:
        """Test models list endpoint."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/v1/models")
                if response.status_code != 200:
                    print(f"  Status code: {response.status_code}")
                    return False
                data = response.json()
                models = data.get("data", [])
                print(f"  Available models: {len(models)}")
                for model in models:
                    print(f"    - {model.get('id')}")
                return len(models) > 0
            except Exception as e:
                print(f"  Error: {e}")
                return False

    async def test_text_response(self) -> bool:
        """Test text-only response."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                payload = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Say hello",
                                }
                            ],
                        }
                    ],
                    "max_new_tokens": 50,
                }
                response = await client.post(
                    f"{self.base_url}/v1/respond",
                    json=payload,
                )
                if response.status_code != 200:
                    print(f"  Status code: {response.status_code}")
                    print(f"  Response: {response.text}")
                    return False
                data = response.json()
                text = data.get("text", "")
                duration_ms = data.get("duration_ms", 0)
                print(f"  Generated: {text[:100]}...")
                print(f"  Duration: {duration_ms}ms")
                return len(text) > 0
            except Exception as e:
                print(f"  Error: {e}")
                return False

    async def test_math_question(self) -> bool:
        """Test math question task."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                payload = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "What is 5 times 5?",
                                }
                            ],
                        }
                    ],
                    "task": "math-5x5",
                    "max_new_tokens": 20,
                }
                response = await client.post(
                    f"{self.base_url}/v1/respond",
                    json=payload,
                )
                if response.status_code != 200:
                    print(f"  Status code: {response.status_code}")
                    return False
                data = response.json()
                text = data.get("text", "").strip()
                print(f"  Response: {text}")
                # Check if response contains "25"
                contains_answer = "25" in text
                print(f"  Contains '25': {contains_answer}")
                return contains_answer
            except Exception as e:
                print(f"  Error: {e}")
                return False


async def main():
    """Main entry point."""
    tester = MultiRuntimeSmokeTester()
    return await tester.run()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
