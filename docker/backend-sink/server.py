#!/usr/bin/env python3
import os
from http.server import HTTPServer, BaseHTTPRequestHandler


class SinkHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        remaining = length
        chunk = 1024 * 1024
        while remaining > 0:
            to_read = min(chunk, remaining)
            data = self.rfile.read(to_read)
            if not data:
                break
            remaining -= len(data)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    httpd = HTTPServer(("0.0.0.0", port), SinkHandler)
    httpd.serve_forever()
