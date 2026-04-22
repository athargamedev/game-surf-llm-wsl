#!/usr/bin/env python
"""Simple web server to serve the chat interface."""

import os
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import threading
from urllib.error import URLError
from urllib.request import urlopen

class CORSRequestHandler(SimpleHTTPRequestHandler):
    """HTTP handler with CORS support for browser requests to the LLM server."""

    def do_GET(self):
        if self.path == "/graph/view":
            self.serve_graph_view()
            return
        super().do_GET()

    def serve_graph_view(self):
        backend_url = "http://127.0.0.1:8000/graph/view"
        fallback_path = Path(__file__).parent / "exports" / "dialogue_relation_graph" / "graph.json"

        try:
            with urlopen(backend_url, timeout=5) as response:
                payload = response.read()
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(payload)
                return
        except URLError:
            pass
        except Exception:
            pass

        if fallback_path.exists():
            payload = fallback_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_error(502, "Graph view unavailable")

    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        """Custom logging."""
        print(f"[{self.client_address[0]}] {format % args}")


def start_web_server(port=8080, directory=None):
    """Start the web server."""
    if directory is None:
        directory = Path(__file__).parent.resolve()
    
    os.chdir(directory)
    
    handler = CORSRequestHandler
    server = HTTPServer(('127.0.0.1', port), handler)
    
    print(f"\n{'='*70}")
    print(f"🌐 Chat Interface Web Server Started")
    print(f"{'='*70}")
    print(f"📍 Open browser: http://127.0.0.1:{port}/chat_interface.html")
    print(f"📁 Serving from: {directory}")
    print(f"🔌 Backend server: http://127.0.0.1:8000")
    print(f"{'='*70}\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✓ Web server stopped")
        server.server_close()


if __name__ == '__main__':
    start_web_server(port=int(os.environ.get("CHAT_SERVER_PORT", "8080")))
