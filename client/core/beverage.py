"""Linked-List로 음료 재고를 관리한다."""
from __future__ import annotations


# 음료 재고 노드: drink_id, 이름, 가격, 재고 수량을 저장하는 Linked-List 원소
class DrinkNode:
    def __init__(self, drink_id, name, price, stock):
        self.drink_id = drink_id
        self.name = name
        self.price = price
        self.stock = stock
        self.next = None  # 다음 노드 포인터

# 음료 재고 관리 클래스: Linked-List로 음료 재고를 관리한다.
class Inventory:
    # 기본 음료 8종 (drink_id, 이름, 가격)
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
    LOW_STOCK_THRESHOLD = 3  # 저재고 알림 기준 수량

    def __init__(self, default_stock: int = 10):
        # 각 음료 재고를 기본값 10개로 초기화
        self.head: DrinkNode | None = None
        for drink_id, name, price in reversed(self.DRINKS):
            self._prepend(drink_id, name, price, default_stock)

    def _prepend(self, drink_id, name, price, stock):
        # 새 노드를 Linked-List 앞에 삽입
        node = DrinkNode(drink_id, name, price, stock)
        node.next = self.head
        self.head = node

# 선형 탐색으로 음료 ID에 해당하는 노드를 찾는 메서드: 판매, 재고 보충, 이름/가격 변경 등에 사용된다.
    def find(self, drink_id: int) -> DrinkNode | None:
        cur = self.head
        while cur:
            if cur.drink_id == drink_id:
                return cur
            cur = cur.next
        return None

    def sell(self, drink_id: int) -> bool:
        node = self.find(drink_id)
        if node is None or node.stock <= 0:
            return False
        node.stock -= 1
        return True

# 관리자 메뉴에서 호출되는 재고 보충 메서드: 음료 ID와 보충할 수량을 받아 해당 음료의 재고를 증가시킨다.
    def restock(self, drink_id: int, amount: int) -> bool:
        node = self.find(drink_id)
        if node is None or amount <= 0:
            return False
        node.stock += amount
        return True

# 관리자 메뉴에서 호출되는 재고 수량 직접 설정 메서드: 음료 ID와 새 재고 수량을 받아 해당 음료의 재고를 설정한다.
    def set_stock(self, drink_id: int, amount: int) -> bool:
        node = self.find(drink_id)
        if node is None:
            return False
        node.stock = max(0, amount)
        return True

# 음료 이름 변경 메서드
    def rename(self, drink_id: int, new_name: str) -> bool:
        node = self.find(drink_id)
        if node is None:
            return False
        node.name = new_name
        return True

# 음료 가격 변경 메서드
    def reprice(self, drink_id: int, new_price: int) -> bool:
        node = self.find(drink_id)
        if node is None:
            return False
        node.price = new_price
        return True

# 저재고 음료 목록 반환 메서드: 재고가 LOW_STOCK_THRESHOLD 미만인 음료 노드들을 리스트로 반환한다.
    def low_stock_list(self) -> list[DrinkNode]:
        result = []
        cur = self.head
        while cur:
            if cur.stock < self.LOW_STOCK_THRESHOLD:
                result.append(cur)
            cur = cur.next
        return result
#투입 금액 기준 구매 가능 음료 목록 반환 매서드
    def available(self, total: int) -> list[DrinkNode]:
        result = []
        cur = self.head
        while cur:
            if cur.price <= total and cur.stock > 0:
                result.append(cur)
            cur = cur.next
        return result

# 현재 재고 상태를 JSON 직렬화용 dict 리스트로 반환하는 메서드: 각 음료 노드의 정보를 딕셔너리로 변환하여 리스트로 반환한다.
    def to_list(self) -> list[dict]:
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
