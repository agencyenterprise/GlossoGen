"""Ephemeral smoke test against the deployed Qwen3-32B endpoint.

Runs inside a Modal container with the vllm-api-key secret attached so the API
key never leaves Modal. Hits chat completion plain + tool-calling variants.
"""

import os

import modal

MODEL_NAME = "Qwen/Qwen3-32B"

image = modal.Image.debian_slim().pip_install("httpx==0.28.1")
app = modal.App("qwen-3-32b-smoke-test")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("vllm-api-key")],
    timeout=15 * 60,
)
def smoke_test(endpoint_base: str) -> None:
    """Hit the chat endpoints (plain + tool) and print results.

    ``endpoint_base`` is resolved locally and passed in rather than read from
    the environment here: Modal re-imports this module inside the container,
    where the caller's shell environment does not exist.

    Retries on HTTP 303 with backoff for up to ~12 minutes, since Modal returns
    303 while the underlying vLLM server is still loading the weights.
    """
    import json
    import os
    import time

    import httpx

    api_key = os.environ["VLLM_API_KEY"]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def post_with_retry(
        client: httpx.Client, path: str, payload: dict[str, object]
    ) -> httpx.Response:
        deadline = time.monotonic() + 12 * 60
        delay = 5
        attempt = 0
        while True:
            attempt += 1
            response = client.post(f"{endpoint_base}{path}", headers=headers, json=payload)
            if response.status_code != 303:
                return response
            elapsed = int(time.monotonic() - (deadline - 12 * 60))
            print(
                f"  attempt {attempt}: HTTP 303 (vLLM still loading), "
                f"waited {elapsed}s, retrying in {delay}s"
            )
            if time.monotonic() + delay > deadline:
                return response
            time.sleep(delay)
            delay = min(delay * 2, 30)

    with httpx.Client(timeout=600.0) as client:
        print("=" * 60)
        print("[1/2] POST /v1/chat/completions  (plain chat)")
        print("=" * 60)
        chat_payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": "Say hello in exactly one word."}],
            "max_tokens": 16,
        }
        response = post_with_retry(client, "/v1/chat/completions", chat_payload)
        print(f"HTTP {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except ValueError:
            print(f"(non-JSON body) {response.text[:500]}")

        print("\n" + "=" * 60)
        print("[2/2] POST /v1/chat/completions  (tool calling)")
        print("=" * 60)
        tool_payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get current weather for a city.",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
            "max_tokens": 128,
        }
        response = post_with_retry(client, "/v1/chat/completions", tool_payload)
        print(f"HTTP {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except ValueError:
            print(f"(non-JSON body) {response.text[:500]}")


@app.local_entrypoint()
def main() -> None:
    """Resolve the endpoint from the local environment and trigger the test.

    Modal returns one hostname per app, namespaced by workspace:
    ``https://<workspace>--qwen-3-32b-serve.modal.run``.
    Set ``MODAL_QWEN_ENDPOINT_BASE`` to yours, with no trailing slash and no ``/v1`` suffix.
    """
    endpoint_base = os.environ.get("MODAL_QWEN_ENDPOINT_BASE")
    if not endpoint_base:
        raise SystemExit(
            "MODAL_QWEN_ENDPOINT_BASE is not set. Point it at your Modal "
            "endpoint, e.g. https://<workspace>--qwen-3-32b-serve.modal.run"
        )
    smoke_test.remote(endpoint_base=endpoint_base.rstrip("/"))
