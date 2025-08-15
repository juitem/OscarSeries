#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple directory web sharing.
Usage:
    python share.py /path/to/dir -p 8000
"""

import os
import sys
import argparse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

def main():
    parser = argparse.ArgumentParser(description="Share a directory over HTTP")
    parser.add_argument("directory", help="Directory to share")
    parser.add_argument("-p", "--port", type=int, default=8000, help="Port to bind (default: 8000)")
    args = parser.parse_args()

    root = os.path.abspath(os.path.expanduser(args.directory))
    if not os.path.isdir(root):
        print(f"Error: not a directory -> {root}", file=sys.stderr)
        sys.exit(2)

    os.chdir(root)

    class Handler(SimpleHTTPRequestHandler):
        def end_headers(self):
            # Allow CORS for convenience
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Serving '{root}' at http://localhost:{args.port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("\nServer stopped.")

if __name__ == "__main__":
    main()