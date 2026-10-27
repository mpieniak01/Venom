"""Deterministic loopback-only LLM for the isolated GitHub E2E job."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "ci-fake-llm"
RESPONSE = "VENOM_E2E_OK_42"
calls = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self.send_json({"models": [{"name": MODEL, "model": MODEL}]})
        elif self.path == "/api/ps":
            self.send_json({"models": [{"name": MODEL, "model": MODEL}]})
        elif self.path == "/v1/models":
            self.send_json(
                {"object": "list", "data": [{"id": MODEL, "object": "model"}]}
            )
        elif self.path == "/__ci_e2e__/calls":
            self.send_json(calls)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        payload = json.loads(
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
        )
        calls.append(payload)
        if payload.get("stream"):
            chunk = {
                "choices": [
                    {"index": 0, "delta": {"content": RESPONSE}, "finish_reason": None}
                ]
            }
            body = ("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_json(
                {
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": RESPONSE},
                            "finish_reason": "stop",
                        }
                    ]
                }
            )


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 11434), Handler).serve_forever()
