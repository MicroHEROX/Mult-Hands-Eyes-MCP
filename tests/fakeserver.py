"""A tiny in-process OpenAI-compatible fake local server for tests."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLocalServer(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, *args):
        pass

    def _reply(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self._reply({"object": "list", "data": [{"id": "local-mm"}]})
        else:
            self._reply({"error": {"message": "not found"}}, 404)

    def do_POST(self):
        assert self.path == "/v1/chat/completions"
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length))
        FakeLocalServer.calls.append(body)
        messages = body["messages"]
        user = messages[-1]
        saw_image = isinstance(user.get("content"), list) and any(
            part.get("type") == "image_url" for part in user["content"]
        )
        text = "IMAGE SEEN: yes" if saw_image else "hello from fake local"
        self._reply(
            {
                "model": "local-mm",
                "choices": [
                    {
                        "message": {
                            "content": text,
                            "reasoning_content": "I thought about it",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            }
        )