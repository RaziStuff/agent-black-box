import json

from agent_black_box.openai import OpenAI


def fake_transport(method, url, headers, body, timeout):
    request_payload = json.loads(body.decode("utf-8"))
    user_message = request_payload["messages"][-1]["content"]
    response = {
        "id": "chatcmpl_demo",
        "object": "chat.completion",
        "model": request_payload["model"],
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"Captured a local demo response for: {user_message}",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21},
    }
    return 200, {"content-type": "application/json"}, json.dumps(response).encode("utf-8")


def main():
    client = OpenAI(
        api_key="demo-key",
        base_url="https://example.invalid/v1",
        transport=fake_transport,
    )
    response = client.chat.completions.create(
        model="demo-model",
        messages=[{"role": "user", "content": "Explain the trace in one line"}],
    )
    print(response.choices[0].message.content)
    print(f"Recorded OpenAI wrapper run: {response.abb_run_id}")
    client.close()


if __name__ == "__main__":
    main()
