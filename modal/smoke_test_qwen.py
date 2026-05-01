"""Ephemeral smoke test against the deployed Qwen3-Next-80B-A3B-Instruct endpoint.

Runs inside a Modal container with the vllm-api-key secret attached so the API
key never leaves Modal. Hits chat completion plain + tool-calling variants.
"""

# mypy: disable-error-code="attr-defined,misc"

import modal

ENDPOINT_BASE = "https://ae-alignment--qwen-3-next-80b-a3b-instruct-serve.modal.run"
MODEL_NAME = "Qwen/Qwen3-Next-80B-A3B-Instruct"

image = modal.Image.debian_slim().pip_install("httpx==0.28.1")
app = modal.App("qwen-3-next-smoke-test")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("vllm-api-key")],
    timeout=15 * 60,
)
def smoke_test() -> None:
    """Hit the chat endpoints (plain + tool) and print results.

    Retries on HTTP 303 with backoff for up to ~12 minutes, since Modal returns
    303 while the underlying vLLM server is still loading the 80B weights.
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
            response = client.post(f"{ENDPOINT_BASE}{path}", headers=headers, json=payload)
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
    """Trigger the remote smoke test."""
    smoke_test.remote()
