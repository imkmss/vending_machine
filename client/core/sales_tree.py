from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SalesNode:
    date:  int          # YYYYMMDD 정수 (BST 키)
    sales: int          # 해당 날짜 총 매출 (원)
    left:  "SalesNode | None" = field(default=None, repr=False)
    right: "SalesNode | None" = field(default=None, repr=False)


class SalesBST:
    """
    날짜(YYYYMMDD 정수)를 키로 매출 데이터를 저장하는 이진 탐색 트리.
    삽입·탐색 평균 O(log n).
    """

    def __init__(self):
        self.root: SalesNode | None = None

    # ------------------------------------------------------------------
    # 삽입
    # ------------------------------------------------------------------
    def insert(self, date: int, sales: int):
        """날짜가 이미 존재하면 매출을 누적합산."""
        self.root = self._insert(self.root, date, sales)

    def _insert(self, node: SalesNode | None, date: int, sales: int) -> SalesNode:
        if node is None:
            return SalesNode(date=date, sales=sales)
        if date < node.date:
            node.left = self._insert(node.left, date, sales)
        elif date > node.date:
            node.right = self._insert(node.right, date, sales)
        else:
            node.sales += sales   # 같은 날짜 → 누적
        return node

    # ------------------------------------------------------------------
    # 탐색
    # ------------------------------------------------------------------
    def search(self, date: int) -> SalesNode | None:
        """이진 탐색으로 해당 날짜 노드 반환. 없으면 None."""
        return self._search(self.root, date)

    def _search(self, node: SalesNode | None, date: int) -> SalesNode | None:
        if node is None:
            return None
        if date == node.date:
            return node
        if date < node.date:
            return self._search(node.left, date)
        return self._search(node.right, date)

    # ------------------------------------------------------------------
    # 범위 조회
    # ------------------------------------------------------------------
    def range_query(self, start: int, end: int) -> list[SalesNode]:
        """start ≤ date ≤ end 범위의 노드를 날짜 오름차순으로 반환."""
        result: list[SalesNode] = []
        self._range(self.root, start, end, result)
        return result

    def _range(self, node: SalesNode | None, start: int, end: int, result: list):
        if node is None:
            return
        if node.date > start:
            self._range(node.left, start, end, result)
        if start <= node.date <= end:
            result.append(node)
        if node.date < end:
            self._range(node.right, start, end, result)

    # ------------------------------------------------------------------
    # 중위 순회 (날짜 오름차순 전체 출력)
    # ------------------------------------------------------------------
    def inorder(self) -> list[SalesNode]:
        result: list[SalesNode] = []
        self._inorder(self.root, result)
        return result

    def _inorder(self, node: SalesNode | None, result: list):
        if node is None:
            return
        self._inorder(node.left, result)
        result.append(node)
        self._inorder(node.right, result)

    # ------------------------------------------------------------------
    # 월별 합산
    # ------------------------------------------------------------------
    def monthly_total(self, year: int, month: int) -> int:
        """YYYY년 MM월 전체 매출 합산."""
        start = year * 10000 + month * 100 + 1
        end   = year * 10000 + month * 100 + 31
        return sum(n.sales for n in self.range_query(start, end))

    def __repr__(self):
        nodes = self.inorder()
        return "SalesBST([" + ", ".join(f"{n.date}:{n.sales}" for n in nodes) + "])"
