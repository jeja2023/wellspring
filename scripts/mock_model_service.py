"""Loopback-only synthetic OpenAI-compatible endpoint, for isolated regression tests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread


def start_mock_model():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            raw = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 200_000))
            data = json.loads(raw)
            calls.append({"path": self.path, "body": data, "authorization": self.headers.get("Authorization", "")})
            model = data.get("model", "")
            status = 401 if model == "synthetic-auth-error" else 200
            output = {"choices": [{"message": {"content": "合成研判结果：资料中的信息需要人工核验。<script>不得执行</script>"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 30, "completion_tokens": 20}}
            if status != 200:
                output = {"error": {"message": "synthetic upstream private detail"}}
            if model == "synthetic-malformed": output = {"choices": []}
            if model == "synthetic-large": output["choices"][0]["message"]["content"] = "x" * 1_100_000
            content = json.dumps(output, ensure_ascii=False).encode()
            self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(content))); self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            authorization = self.headers.get("Authorization", "")
            calls.append({"path":self.path,"body":None,"authorization":authorization})
            status = 401 if authorization=='Bearer synthetic-bad-key' else 200
            payload = {"object":"list","data":[{"id":"synthetic-model"},{"id":"synthetic-other-model"},{"id":"synthetic-model"}]} if status==200 else {"error":"private upstream detail"}
            content=json.dumps(payload).encode()
            self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(content)));self.end_headers();self.wfile.write(content)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, calls
