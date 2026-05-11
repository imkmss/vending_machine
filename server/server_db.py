from __future__ import annotations

import threading

from client.core.sales_tree import SalesBST, SalesNode


class SalesDataStore:
    """Thread-safe 서버 측 클라이언트별 매출 BST 저장소."""

    def __init__(self):
        self._bst: dict[str, SalesBST] = {}  # client_id → SalesBST
        self._lock = threading.Lock()

    def record_sale(self, client_id: str, date_str: str, price: int) -> None:
        """판매 데이터를 해당 클라이언트의 BST에 삽입."""
        date_int = int(date_str.replace("-", ""))
        with self._lock:
            if client_id not in self._bst:
                self._bst[client_id] = SalesBST()
            self._bst[client_id].insert(date_int, price)

    def range_query(self, client_id: str, start: int, end: int) -> list[SalesNode]:
        """start~end 날짜 범위 매출 조회."""
        with self._lock:
            bst = self._bst.get(client_id)
            return bst.range_query(start, end) if bst else []

    def all_clients(self) -> list[str]:
        with self._lock:
            return list(self._bst.keys())
