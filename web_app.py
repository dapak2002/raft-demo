#!/usr/bin/env python3
"""Simple web UI for the order query agent with live node progress."""

import json
import logging
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from agent.graph import PIPELINE_NODES, iter_stream_events, run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("langgraph.pregel._retry").setLevel(logging.WARNING)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/pipeline")
def pipeline():
    return jsonify({"nodes": list(PIPELINE_NODES)})


@app.post("/api/query")
def query():
    body = request.get_json(silent=True) or {}
    user_query = (body.get("query") or "").strip()
    if not user_query:
        return jsonify(
            {"status": "error", "error": "Query is required.", "orders": []}
        ), 400

    try:
        return jsonify(run(user_query))
    except RuntimeError as exc:
        return jsonify({"status": "error", "error": str(exc), "orders": []}), 500


@app.post("/api/query/stream")
def query_stream():
    body = request.get_json(silent=True) or {}
    user_query = (body.get("query") or "").strip()
    if not user_query:
        return jsonify({"error": "Query is required."}), 400

    def generate():
        try:
            for event in iter_stream_events(user_query):
                yield f"data: {json.dumps(event)}\n\n"
        except RuntimeError as exc:
            payload = {"event": "error", "message": str(exc)}
            yield f"data: {json.dumps(payload)}\n\n"
            done = {
                "event": "done",
                "result": {
                    "status": "error",
                    "error": str(exc),
                    "user_query": user_query,
                    "data_query": None,
                    "orders": [],
                },
            }
            yield f"data: {json.dumps(done)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True, threaded=True)
