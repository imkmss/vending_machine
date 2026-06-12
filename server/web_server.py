"""
서버 측 관리 메뉴 웹 페이지: 매출·재고 현황을 브라우저에서 조회할 수 있다.

VendingServer와 SalesDataStore 인스턴스를 공유하며,
별도 스레드에서 Flask를 실행한다.

  브라우저 → http://localhost:8080
"""
from __future__ import annotations

import threading
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request

from server.server_db import SalesDataStore

app = Flask(__name__)
_store: SalesDataStore | None = None   # server_main에서 주입


def _get_store() -> SalesDataStore:
    assert _store is not None, "SalesDataStore가 주입되지 않았습니다."
    return _store


# ── 대시보드 HTML ───────────────────────────────────
@app.route("/")
def index():
    clients = _get_store().all_clients()
    return render_template("dashboard.html", clients=clients)


# ── API: 연결된 자판기 목록 ─────────────────────────
@app.route("/api/clients")
def api_clients():
    return jsonify(_get_store().all_clients())


# ── API: 월별 매출 (최근 6개월) ────────────────────
@app.route("/api/monthly")
def api_monthly():
    client_id = request.args.get("client_id", "")
    store = _get_store()

    today = date.today()
    labels, values = [], []
    for i in range(5, -1, -1):
        month = today.month - i
        year  = today.year
        while month <= 0:
            month += 12
            year  -= 1
        labels.append(f"{year}-{month:02d}")
        values.append(store.monthly_summary(client_id, year, month))

    return jsonify({"labels": labels, "values": values})


# ── API: 일별 매출 (최근 14일) ─────────────────────
@app.route("/api/daily")
def api_daily():
    client_id = request.args.get("client_id", "")
    store = _get_store()

    from datetime import timedelta
    today  = date.today()
    labels, values = [], []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        date_int = int(d.strftime("%Y%m%d"))
        labels.append(d.strftime("%m-%d"))
        values.append(store.daily_summary(client_id, date_int))

    return jsonify({"labels": labels, "values": values})


# ── API: 음료별 매출 분석 ───────────────────────────
@app.route("/api/breakdown")
def api_breakdown():
    client_id = request.args.get("client_id", "")
    today = date.today()
    start = int(f"{today.year}0101")
    end   = int(f"{today.year}1231")
    data  = _get_store().drink_breakdown(client_id, start, end)

    labels  = list(data.keys())
    counts  = [data[k]["count"]  for k in labels]
    amounts = [data[k]["amount"] for k in labels]
    return jsonify({"labels": labels, "counts": counts, "amounts": amounts})


# ── API: 재고 현황 ──────────────────────────────────
@app.route("/api/inventory")
def api_inventory():
    client_id = request.args.get("client_id", "")
    return jsonify(_get_store().get_inventory(client_id))


# ── 서버 시작 함수 (server_main에서 호출) ───────────
def start_web_server(data_store: SalesDataStore, host: str = "0.0.0.0", port: int = 8080):
    global _store
    _store = data_store
    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True,
        name="web",
    )
    t.start()
    print(f"[웹] 대시보드 시작 — http://localhost:{port}")
