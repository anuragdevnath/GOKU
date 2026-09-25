#!/usr/bin/env python3
"""
app.py — local web UI for the activity report.

Run with:
    python app.py

Then open http://127.0.0.1:5050 in your browser.

This runs ONLY on your own machine (localhost) — it is not exposed to the
internet, which matters since it uses your GitHub token and Gmail login.
"""

from flask import Flask, jsonify, render_template, request

from fetchers import fetch_all

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/report")
def api_report():
    start = request.args.get("start")
    end = request.args.get("end")
    skip_github = request.args.get("skip_github") == "true"
    skip_gmail = request.args.get("skip_gmail") == "true"
    skip_slack = request.args.get("skip_slack") == "true"
    skip_chat = request.args.get("skip_chat") == "true"

    if not start or not end:
        return jsonify({"error": "start and end dates are required"}), 400
    if start > end:
        return jsonify({"error": "start date must be before end date"}), 400

    try:
        report = fetch_all(
            start, end,
            skip_github=skip_github,
            skip_gmail=skip_gmail,
            skip_slack=skip_slack,
            skip_chat=skip_chat,
        )
    except Exception as exc:  # surface a readable error in the UI instead of a 500 wall
        return jsonify({"error": str(exc)}), 500

    return jsonify({"report": report})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
