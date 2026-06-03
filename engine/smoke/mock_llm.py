"""
Mock LLM SSE server — a stand-in brain so the end-to-end smoke needs no API key.

Responds to any POST with a short streamed reply in LVP's generic SSE shape:
  data: {"token": "..."}      (one per word)
  data: {"done": true, "full": "..."}

Run:  python mock_llm.py [port]      (default 3099)
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

REPLY = "Oi! Eu ouvi você muito bem. Tudo certo por aqui."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_POST(self):
        n = int(self.headers.get('Content-Length', '0'))
        self.rfile.read(n)
        print('[mock-llm] POST received — streaming reply', flush=True)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for word in REPLY.split(' '):
            self.wfile.write(f'data: {json.dumps({"token": word + " "})}\n\n'.encode())
            self.wfile.flush()
        self.wfile.write(f'data: {json.dumps({"done": True, "full": REPLY})}\n\n'.encode())
        self.wfile.flush()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3099
    print(f'[mock-llm] listening on http://127.0.0.1:{port}', flush=True)
    HTTPServer(('127.0.0.1', port), Handler).serve_forever()
