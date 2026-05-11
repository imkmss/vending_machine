from __future__ import annotations


class DrinkNode:
    def __init__(self, drink_id, name, price, stock):
        self.drink_id = drink_id
        self.name = name
        self.price = price
        self.stock = stock
        self.next = None


class Inventory:
    """음료 재고 목록을 단방향 Linked List로 관리."""

    DRINKS = [
        (1, "믹스커피",    200),
        (2, "고급믹스커피", 300),
        (3, "물",          450),
        (4, "캔커피",      500),
        (5, "이온음료",    550),
        (6, "고급캔커피",  700),
        (7, "탄산음료",    750),
        (8, "특화음료",    800),
    ]
    LOW_STOCK_THRESHOLD = 3

    def __init__(self, default_stock: int = 10):
        self.head: DrinkNode | None = None
        for drink_id, name, price in reversed(self.DRINKS):
            self._prepend(drink_id, name, price, default_stock)

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------
    def _prepend(self, drink_id, name, price, stock):
        node = DrinkNode(drink_id, name, price, stock)
        node.next = self.head
        self.head = node

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------
    def find(self, drink_id: int) -> DrinkNode | None:
        """선형 탐색으로 drink_id에 해당하는 노드 반환."""
        cur = self.head
        while cur:
            if cur.drink_id == drink_id:
                return cur
            cur = cur.next
        return None

    def sell(self, drink_id: int) -> bool:
        """재고 1 차감. 성공 시 True, 재고 없거나 음료 없으면 False."""
        node = self.find(drink_id)
        if node is None or node.stock <= 0:
            return False
        node.stock -= 1
        return True

    def restock(self, drink_id: int, amount: int) -> bool:
        node = self.find(drink_id)
        if node is None or amount <= 0:
            return False
        node.stock += amount
        return True

    def set_stock(self, drink_id: int, amount: int) -> bool:
        node = self.find(drink_id)
        if node is None:
            return False
        node.stock = max(0, amount)
        return True

    def rename(self, drink_id: int, new_name: str) -> bool:
        """서버 COMMAND(0x06) 수신 시 음료 이름 변경."""
        node = self.find(drink_id)
        if node is None:
            return False
        node.name = new_name
        return True

    def low_stock_list(self) -> list[DrinkNode]:
        """재고가 LOW_STOCK_THRESHOLD 미만인 음료 목록 반환."""
        result = []
        cur = self.head
        while cur:
            if cur.stock < self.LOW_STOCK_THRESHOLD:
                result.append(cur)
            cur = cur.next
        return result

    def available(self, total: int) -> list[DrinkNode]:
        """투입 금액(total) 기준 구매 가능 음료 목록 반환."""
        result = []
        cur = self.head
        while cur:
            if cur.price <= total and cur.stock > 0:
                result.append(cur)
            cur = cur.next
        return result

    def to_list(self) -> list[dict]:
        """현재 재고 상태를 JSON 직렬화용 dict 리스트로 반환."""
        result = []
        cur = self.head
        while cur:
            result.append({
                "drink_id": cur.drink_id,
                "name": cur.name,
                "price": cur.price,
                "stock": cur.stock,
            })
            cur = cur.next
        return result

    def __repr__(self):
        parts = []
        cur = self.head
        while cur:
            parts.append(f"[{cur.name}|{cur.price}원|재고{cur.stock}]")
            cur = cur.next
        return " → ".join(parts) + " → None"
