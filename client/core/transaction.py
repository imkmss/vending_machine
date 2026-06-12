"""화폐 투입·음료 선택·거스름돈 반환 등 판매 처리와 서버 전송 Queue를 관리한다."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import ctypes
import datetime
import time

from client.core.beverage import DrinkNode, Inventory
from client.core.coin_manager import (
    CoinSlot, ChangeStack, ChangeReserve,
    init_coin, insert_coin, get_inserted_coins, release_coin,
    OK, INVALID_UNIT, BILL_LIMIT, TOTAL_LIMIT,
)
from client.data.file_manager import append_stock_exhaustion


# ──────────────────────────────────────────────
# 판매 레코드
# ──────────────────────────────────────────────
@dataclass
class SaleRecord:
    client_id:   str
    date:        str          # "YYYY-MM-DD"
    sold_drink:  dict         # {drink_id, name, price}
    daily_sales: int          # 해당 자판기 하루 누적 매출 (원)
    inventory:   list[dict]   # 8종 현재 재고 스냅샷
    timestamp:   float = field(default_factory=time.time)
    retry_count: int = 0


# ──────────────────────────────────────────────
# 서버 전송 대기열 (Queue)
# ──────────────────────────────────────────────
class SendQueue:
    """판매 레코드를 서버로 전송하기 위한 Queue 자료구조."""

    MAX_RETRIES = 3

    def __init__(self):
        self._queue: deque[SaleRecord] = deque()

    def enqueue(self, record: SaleRecord):
        self._queue.append(record)

    def dequeue(self) -> SaleRecord | None:
        return self._queue.popleft() if self._queue else None

    def requeue(self, record: SaleRecord):
        """전송 실패 시 retry_count 증가 후 큐 앞에 재삽입."""
        record.retry_count += 1
        self._queue.appendleft(record)

    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def size(self) -> int:
        return len(self._queue)

    def peek(self) -> SaleRecord | None:
        return self._queue[0] if self._queue else None

    def __repr__(self):
        return f"SendQueue(size={len(self._queue)})"


# ──────────────────────────────────────────────
# 자판기 트랜잭션 관리자
# ──────────────────────────────────────────────
class VendingSession:
    """자판기 1회 이용 세션: 화폐 투입부터 음료 배출·거스름돈 반환까지 처리한다."""

    def __init__(self, client_id: str, inventory: Inventory, send_queue: SendQueue,
                 reserve: ChangeReserve | None = None):
        self.client_id   = client_id
        self.inventory   = inventory
        self.send_queue  = send_queue
        self.reserve     = reserve or ChangeReserve()
        self.daily_sales = 0

        self._coin: ctypes.POINTER(CoinSlot) | None = None

    # ── 화폐 투입 ──────────────────────────────
    def insert_coin(self, amount: int) -> int:
        """
        화폐 투입. 첫 투입 시 CoinSlot 동적 할당.
        반환값: OK / INVALID_UNIT / BILL_LIMIT / TOTAL_LIMIT
        """
        if self._coin is None:
            self._coin = init_coin()
        return insert_coin(self._coin, amount)

    @property
    def total(self) -> int:
        return self._coin.contents.total if self._coin else 0

    def available_drinks(self) -> list[DrinkNode]:
        """현재 투입 금액으로 살 수 있는 음료 목록."""
        return self.inventory.available(self.total)

    # ── 음료 선택 ──────────────────────────────
    def select_drink(self, drink_id: int) -> tuple[bool, ChangeStack | None, str]:
        """
        음료 선택 처리.
        반환: (성공 여부, 거스름돈 스택 또는 None, 메시지)
        성공 시 SaleRecord를 SendQueue에 enqueue하고 CoinSlot 해제.
        """
        if self._coin is None or self.total == 0:
            return False, None, "투입 금액이 없습니다."

        node = self.inventory.find(drink_id)
        if node is None:
            return False, None, "존재하지 않는 음료입니다."
        if node.stock <= 0:
            return False, None, f"{node.name} 재고가 없습니다."
        if self.total < node.price:
            return False, None, f"금액이 부족합니다. ({self.total}원 < {node.price}원)"

        # 거스름돈 가능 여부 확인
        change_amount = self.total - node.price
        if change_amount > 0 and not self.reserve.can_make_change(change_amount):
            return False, None, (
                f"거스름돈({change_amount:,}원)이 부족합니다.\n정확한 금액을 투입해 주세요."
            )

        # 재고 차감
        self.inventory.sell(drink_id)

        # 재고 소진 시 날짜 기록
        if node.stock == 0:
            append_stock_exhaustion(
                date_str=datetime.date.today().isoformat(),
                client_id=self.client_id,
                drink_id=node.drink_id,
                drink_name=node.name,
            )

        # 투입 동전 → 보유고 편입 후 거스름돈 지급
        self.reserve.accept_coins(self._coin)
        change_stack = self.reserve.give_change(change_amount)

        # 매출 누적
        self.daily_sales += node.price

        # 판매 레코드 생성 → 큐 삽입
        record = SaleRecord(
            client_id=self.client_id,
            date=datetime.date.today().isoformat(),
            sold_drink={"drink_id": node.drink_id, "name": node.name, "price": node.price},
            daily_sales=self.daily_sales,
            inventory=self.inventory.to_list(),
        )
        self.send_queue.enqueue(record)

        # CoinSlot 해제
        release_coin(self._coin)
        self._coin = None

        return True, change_stack, f"{node.name} 판매 완료. 거스름돈: {change_amount}원"

    # ── 반환 버튼 ──────────────────────────────
    def refund(self) -> ChangeStack | None:
        """투입된 화폐를 넣은 단위 그대로 반환. CoinSlot 해제."""
        if self._coin is None or self.total == 0:
            return None
        change_stack = get_inserted_coins(self._coin)
        release_coin(self._coin)
        self._coin = None
        return change_stack

    # ── 하루 매출 초기화 ───────────────────────
    def reset_daily_sales(self):
        self.daily_sales = 0
