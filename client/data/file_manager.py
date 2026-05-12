from __future__ import annotations

import csv
import os
from datetime import date

DEFAULT_PATH    = os.path.join(os.path.dirname(__file__), "sales_log.csv")
FIELDNAMES      = ["date", "client_id", "drink_id", "drink_name", "price", "daily_sales"]

RESTOCK_PATH    = os.path.join(os.path.dirname(__file__), "restock_log.csv")
RESTOCK_FIELDS  = ["date", "client_id", "drink_id", "drink_name", "amount"]


def _ensure_header(path: str):
    """파일이 없거나 비어있으면 CSV 헤더를 기록한다."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def append_sale(
    date_str:    str,
    client_id:   str,
    drink_id:    int,
    drink_name:  str,
    price:       int,
    daily_sales: int,
    path:        str = DEFAULT_PATH,
):
    """판매 확정 시 CSV에 한 줄 추가. 서버 전송 실패와 무관하게 항상 로컬 기록."""
    _ensure_header(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow({
            "date":        date_str,
            "client_id":   client_id,
            "drink_id":    drink_id,
            "drink_name":  drink_name,
            "price":       price,
            "daily_sales": daily_sales,
        })


def load_sales(path: str = DEFAULT_PATH) -> list[dict]:
    """CSV 전체를 읽어 dict 리스트로 반환. BST 초기 로딩에 사용."""
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def append_restock(
    date_str:   str,
    client_id:  str,
    drink_id:   int,
    drink_name: str,
    amount:     int,
    path:       str = RESTOCK_PATH,
):
    """재고 보충 이벤트를 CSV에 기록."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=RESTOCK_FIELDS).writeheader()
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=RESTOCK_FIELDS).writerow({
            "date": date_str, "client_id": client_id,
            "drink_id": drink_id, "drink_name": drink_name, "amount": amount,
        })


COLLECTION_PATH   = os.path.join(os.path.dirname(__file__), "collection_log.csv")
COLLECTION_FIELDS = ["collected_at", "client_id", "start_date", "end_date", "mode", "amount"]


def append_collection(
    collected_at: str,
    client_id:    str,
    start_date:   str,
    end_date:     str,
    mode:         str,
    amount:       int,
    path:         str = COLLECTION_PATH,
):
    """수금 이벤트를 CSV에 기록."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLLECTION_FIELDS).writeheader()
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=COLLECTION_FIELDS).writerow({
            "collected_at": collected_at,
            "client_id":    client_id,
            "start_date":   start_date,
            "end_date":     end_date,
            "mode":         mode,
            "amount":       amount,
        })


def load_restocks(path: str = RESTOCK_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_collections(path: str = COLLECTION_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_daily_total(client_id: str, date_str: str, path: str = DEFAULT_PATH) -> int:
    """
    특정 자판기·날짜의 매출 합산.
    프로세스 재시작 시 daily_sales를 복원하는 데 사용.
    """
    total = 0
    for row in load_sales(path):
        if row["client_id"] == client_id and row["date"] == date_str:
            total += int(row["price"])
    return total
