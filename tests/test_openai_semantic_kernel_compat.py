"""Fresh-process compatibility probe for the real MAF/OpenAI SDK stack.

The historical filename remains registered in the release catalog. No legacy
SDK shim is imported and no provider/SDK classes are replaced by mocks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_maf_openai_connector_executes_with_installed_sdk_stack() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = dedent(
        """
        import asyncio
        import json
        import sys
        import httpx
        from openai import AsyncOpenAI
        from agent_framework import Message
        from agent_framework_openai import OpenAIChatCompletionClient

        async def main():
            requests = []
            def respond(request):
                assert str(request.url) == 'http://sdk-probe.invalid/v1/chat/completions'
                requests.append(json.loads(request.content))
                return httpx.Response(200, json={
                    'id': 'sdk-probe', 'object': 'chat.completion',
                    'created': 1, 'model': 'probe-model',
                    'choices': [{'index': 0, 'finish_reason': 'stop',
                                 'message': {'role': 'assistant', 'content': 'MAF ready'}}],
                })
            # Only HTTP transport is isolated: real MAF, OpenAI and Pydantic
            # constructors, serialization and response parsing all execute.
            transport = httpx.AsyncClient(transport=httpx.MockTransport(respond))
            async with AsyncOpenAI(
                api_key='local-sdk-probe', base_url='http://sdk-probe.invalid/v1',
                http_client=transport, max_retries=0,
            ) as sdk:
                client = OpenAIChatCompletionClient(model='probe-model', async_client=sdk)
                result = await client.get_response(
                    [Message(role='user', contents=['protocol probe'])],
                    options={'temperature': 0.2, 'max_tokens': 8},
                )
                assert result.text == 'MAF ready'
                assert len(requests) == 1
                assert requests[0]['model'] == 'probe-model'
                assert requests[0]['messages'][0]['content'] == 'protocol probe'
                assert requests[0]['temperature'] == 0.2
                assert requests[0]['max_completion_tokens'] == 8
            assert not any(name == 'semantic_kernel' or name.startswith('semantic_kernel.')
                           for name in sys.modules)
            print('REAL_MAF_OPENAI_PROTOCOL_PASS')

        asyncio.run(main())
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "REAL_MAF_OPENAI_PROTOCOL_PASS" in result.stdout
