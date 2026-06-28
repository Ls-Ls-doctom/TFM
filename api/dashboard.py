from http.server import BaseHTTPRequestHandler
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "pag_web"
sys.path.insert(0, str(ROOT / "Procesos"))
sys.path.insert(0, str(ROOT / "LMlocal"))

from sql_data import DATA_API_URL, remote_request


def cloud_dashboard_payload():
    if not DATA_API_URL:
        from server import build_dashboard_payload

        return build_dashboard_payload()
    return remote_request("dashboard")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            payload = cloud_dashboard_payload()
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
