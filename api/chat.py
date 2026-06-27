from http.server import BaseHTTPRequestHandler
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "pag_web"
sys.path.insert(0, str(ROOT / "Procesos"))
sys.path.insert(0, str(ROOT / "LMlocal"))

from server import (
    read_json_body,
    build_trace,
    answer_memory_question,
    compact_history,
    call_lm_studio,
    chunk_answer,
    should_use_data_context,
)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            payload = read_json_body(self)
            question = str(payload.get("message", ""))
            history = compact_history(payload.get("history", []))
            memory_answer = answer_memory_question(question, history)
            answer = memory_answer or call_lm_studio(payload)
            trace = build_trace(payload)
            body = json.dumps(
                {"answer": answer, "provider": "groq", "trace": trace},
                ensure_ascii=False,
            ).encode("utf-8")
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
