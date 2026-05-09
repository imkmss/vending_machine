from __future__ import annotations

import ctypes

# ------------------------------------------------------------------
# 오류 코드
# ------------------------------------------------------------------
OK           = 0
INVALID_UNIT = 1  # 허용되지 않는 화폐 단위
BILL_LIMIT   = 2  # 지폐(1,000원) 누적 한도 초과
TOTAL_LIMIT  = 3  # 총 투입 한도 초과

VALID_UNITS  = [10, 50, 100, 500, 1000]
UNIT_INDEX   = {10: 0, 50: 1, 100: 2, 500: 3, 1000: 4}
CHANGE_UNITS = [500, 100, 50, 10]

MAX_BILL_TOTAL = 5000   # 지폐 누적 상한 (원)
MAX_TOTAL      = 7000   # 총 투입 상한 (원)


# ------------------------------------------------------------------
# CoinSlot — ctypes 구조체 (C 호환 메모리 레이아웃)
# ------------------------------------------------------------------
class CoinSlot(ctypes.Structure):
    _fields_ = [
        ("slot",       ctypes.c_int * 5),   # 0→10, 1→50, 2→100, 3→500, 4→1000 단위별 개수
        ("total",      ctypes.c_int),        # 현재 총 투입 금액
        ("bill_total", ctypes.c_int),        # 1,000원권 누적 금액
    ]


# ------------------------------------------------------------------
# ChangeStack — 거스름돈 계산용 Stack
# ------------------------------------------------------------------
class ChangeStack:
    def __init__(self):
        self._stack: list[tuple[int, int]] = []

    def push(self, unit: int, count: int):
        self._stack.append((unit, count))

    def pop(self) -> tuple[int, int] | None:
        return self._stack.pop() if self._stack else None

    def is_empty(self) -> bool:
        return len(self._stack) == 0

    def __repr__(self):
        return f"ChangeStack({self._stack})"


# ------------------------------------------------------------------
# 공개 함수
# ------------------------------------------------------------------
def init_coin() -> ctypes.POINTER(CoinSlot):
    """CoinSlot을 ctypes로 동적 할당하고 0 초기화 후 포인터 반환."""
    ptr = ctypes.cast(
        ctypes.create_string_buffer(ctypes.sizeof(CoinSlot)),
        ctypes.POINTER(CoinSlot),
    )
    ptr.contents.total = 0
    ptr.contents.bill_total = 0
    for i in range(5):
        ptr.contents.slot[i] = 0
    return ptr


def insert_coin(coin: ctypes.POINTER(CoinSlot), amount: int) -> int:
    """
    화폐 투입 처리.
    반환값: OK(0) / INVALID_UNIT(1) / BILL_LIMIT(2) / TOTAL_LIMIT(3)
    """
    if amount not in VALID_UNITS:
        return INVALID_UNIT

    if amount == 1000 and coin.contents.bill_total + 1000 > MAX_BILL_TOTAL:
        return BILL_LIMIT

    if coin.contents.total + amount > MAX_TOTAL:
        return TOTAL_LIMIT

    idx = UNIT_INDEX[amount]
    coin.contents.slot[idx] += 1
    coin.contents.total += amount
    if amount == 1000:
        coin.contents.bill_total += 1000

    return OK


def calc_change(remain: int) -> ChangeStack:
    """
    잔액(remain)을 큰 단위부터 그리디로 나눠 ChangeStack에 push.
    Stack에서 pop하면 큰 단위부터 꺼낼 수 있도록 작은 단위를 먼저 push.
    """
    stack = ChangeStack()
    for unit in CHANGE_UNITS:   # 500 → 100 → 50 → 10 순으로 push (pop하면 큰 단위부터)
        count = remain // unit
        remain %= unit
        if count > 0:
            stack.push(unit, count)
    return stack


def release_coin(coin: ctypes.POINTER(CoinSlot)) -> None:
    """CoinSlot 메모리를 해제하고 None을 반환 (호출 측에서 변수에 None 대입)."""
    del coin
