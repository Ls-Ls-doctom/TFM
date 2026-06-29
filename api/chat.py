from http.server import BaseHTTPRequestHandler
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent / "pag_web"
sys.path.insert(0, str(ROOT / "Procesos"))

from gemini_data import answer_with_gemini, answer_with_gemini_stream, compact_history


def read_json_body(request_handler: BaseHTTPRequestHandler) -> dict:
    length = int(request_handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = request_handler.rfile.read(length)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return json.loads(text)


def memory_answer(question: str, history: list[dict[str, str]]) -> str | None:
    normalized = question.lower()
    user_messages = [item["content"] for item in history if item["role"] == "user"]
    if not user_messages:
        return None
    if "qué te pregunté primero" in normalized or "que te pregunte primero" in normalized:
        return f'Lo primero que me preguntaste fue: "{user_messages[0]}".'
    if "pregunta anterior" in normalized:
        if len(user_messages) <= 1:
            return None
        return f'Tu pregunta anterior fue: "{user_messages[-2]}".'
    return None


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
            question = str(payload.get("message", "")).strip()
            history = compact_history(payload.get("history", []))
            payload["history"] = history
            use_stream = bool(payload.get("stream", False))

            mem = memory_answer(question, history)
            if mem:
                if use_stream:
                    self._sse_headers()
                    self._send_event("delta", {"text": mem})
                    self._send_event("meta", {"provider": "google", "model": "memory",
                                              "usesData": False, "rows": 0, "queryRows": []})
                    self._send_event("done", {"finishReason": "stop"})
                else:
                    trace = {"provider": "google", "model": "memory",
                             "usesData": False, "rows": 0, "queryRows": []}
                    self._json({"answer": mem, "provider": "google-gemini", "trace": trace})
                return

            if use_stream:
                self._sse_headers()
                try:
                    for event_name, event_data in answer_with_gemini_stream(payload):
                        self._send_event(event_name, event_data)
                except Exception as error:  # noqa: BLE001
                    self._send_event(
                        "error",
                        {
                            "error": "No se pudo completar la consulta.",
                            "detail": str(error)[:800],
                        },
                    )
                finally:
                    self.close_connection = True
                return
            else:
                answer, trace = answer_with_gemini(payload)
                self._json({"answer": answer, "provider": "google-gemini", "trace": trace})

        except Exception as error:  # noqa: BLE001
            body = json.dumps(
                {"error": "No se pudo generar la respuesta.", "detail": str(error)[:800]},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _send_event(self, event_name: str, data: dict):
        line = f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        self.wfile.write(line.encode("utf-8"))
        try:
            self.wfile.flush()
        except Exception:  # noqa: BLE001
            pass

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
