"""서버 측 자판기별 매출 BST 및 재고 현황을 스레드 안전하게 저장한다."""
from __future__ import annotations

import threading

from client.core.sales_tree import SalesBST, SalesNode
from client.core.sort_search import binary_search_sales


class SalesDataStore:
    """자판기별 일별/월별 매출 합산·누적합산 및 실시간 재고 현황을 관리한다."""

    def __init__(self):
        self._bst:       dict[str, SalesBST]    = {}  # client_id → SalesBST
        self._inventory: dict[str, list[dict]]  = {}  # client_id → 최신 재고 스냅샷
        self._lock = threading.Lock()

    def record_sale(self, client_id: str, date_str: str, price: int,
                    drink_name: str = "", drink_price: int = 0) -> None:
        """판매 데이터를 해당 클라이언트의 BST에 삽입 (음료별 집계 포함)."""
        date_int = int(date_str.replace("-", ""))
        with self._lock:
            if client_id not in self._bst:
                self._bst[client_id] = SalesBST()
            self._bst[client_id].insert(date_int, price, drink_name, drink_price)

    def range_query(self, client_id: str, start: int, end: int) -> list[SalesNode]:
        """start~end 날짜 범위 매출 조회."""
        with self._lock:
            bst = self._bst.get(client_id)
            return bst.range_query(start, end) if bst else []

    def drink_breakdown(self, client_id: str, start: int, end: int) -> dict:
        """start~end 범위 음료별 판매 수·금액 집계."""
        nodes = self.range_query(client_id, start, end)
        result: dict[str, dict] = {}
        for node in nodes:
            for name, data in node.by_drink.items():
                entry = result.setdefault(name, {"count": 0, "amount": 0})
                entry["count"]  += data["count"]
                entry["amount"] += data["amount"]
        return result

    # ── SV102: 일별/월별 매출 합산 ──────────────────
    def daily_summary(self, client_id: str, date_int: int) -> int:
        """특정 날짜(YYYYMMDD) 총 매출 — binary_search_sales로 정렬 배열 탐색."""
        with self._lock:
            bst = self._bst.get(client_id)
            if bst is None:
                return 0
            node = binary_search_sales(bst.inorder(), date_int)
            return node.sales if node else 0

    def monthly_summary(self, client_id: str, year: int, month: int) -> int:
        """특정 월 총 매출."""
        with self._lock:
            bst = self._bst.get(client_id)
            return bst.monthly_total(year, month) if bst else 0

    # ── SV103: 재고 현황 저장 ────────────────────
    def update_inventory(self, client_id: str, inventory: list[dict]) -> None:
        """자판기 최신 재고 스냅샷 갱신."""
        with self._lock:
            self._inventory[client_id] = list(inventory)

    def get_inventory(self, client_id: str) -> list[dict]:
        """자판기 최신 재고 현황 반환."""
        with self._lock:
            return list(self._inventory.get(client_id, []))

    def all_clients(self) -> list[str]:
        with self._lock:
            return list(self._bst.keys())
