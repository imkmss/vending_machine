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
# ctypes 포인터는 Pylance 타입 시스템과 호환되지 않으므로
# coin 파라미터 어노테이션 생략 (ctypes 관행)
# ------------------------------------------------------------------
def init_coin():
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


def insert_coin(coin, amount: int) -> int:
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
    pop하면 큰 단위부터 나온다.
    음료 구매 후 거스름돈 계산에 사용.
    """
    stack = ChangeStack()
    for unit in CHANGE_UNITS:   # 500 → 100 → 50 → 10 순으로 push
        count = remain // unit
        remain %= unit
        if count > 0:
            stack.push(unit, count)
    return stack


def get_inserted_coins(coin) -> ChangeStack:
    """
    사용자가 실제로 투입한 화폐를 단위별 개수 그대로 ChangeStack에 담아 반환.
    반환 버튼 시 사용 — 그리디 분해 없이 slot[] 값을 그대로 읽는다.
    push 순서: 10 → 50 → 100 → 500 → 1000 (pop하면 큰 단위부터 나옴)
    """
    stack = ChangeStack()
    for i, unit in enumerate(VALID_UNITS):   # 0→10, 1→50, 2→100, 3→500, 4→1000
        count = coin.contents.slot[i]
        if count > 0:
            stack.push(unit, count)
    return stack


def release_coin(coin) -> None:
    """CoinSlot 메모리를 해제한다 (호출 측에서 변수에 None 대입)."""
    del coin


# ------------------------------------------------------------------
# ChangeReserve — 자판기 내 잔돈 보유고
# ------------------------------------------------------------------
RESERVE_DENOMS = [500, 100, 50, 10]   # 거스름돈으로 사용하는 단위 (큰 것부터)
MIN_RESERVE    = 3                     # 수금 후 각 단위 최소 유지 개수


class ChangeReserve:
    """
    자판기 내 동전 보유고.
    거스름돈 단위(10·50·100·500원)는 각 10개로 초기화 (PDF 요건).
    1000원권은 거스름돈으로 사용하지 않으며 별도 집계만 한다.
    """

    INITIAL = 10   # 각 동전 단위 초기 보유 수량

    def __init__(self):
        # 거스름돈 단위별 보유 수량
        self._coins: dict[int, int] = {
            10:   self.INITIAL,
            50:   self.INITIAL,
            100:  self.INITIAL,
            500:  self.INITIAL,
            1000: 0,   # 지폐 — 거스름돈으로 사용 안 함, 집계용
        }

    # ── 조회 ────────────────────────────────────────────────────
    def status(self) -> dict[int, int]:
        """단위별 보유 수량 반환 (읽기 전용 복사본)."""
        return dict(self._coins)

    def total_amount(self) -> int:
        """보유고 총 금액(원) 반환."""
        return sum(unit * cnt for unit, cnt in self._coins.items())

    # ── 거스름돈 가능 여부 확인 ─────────────────────────────────
    def can_make_change(self, amount: int) -> bool:
        """amount원 거스름돈을 현재 보유고로 줄 수 있는지 시뮬레이션."""
        remain = amount
        for unit in RESERVE_DENOMS:
            count = min(remain // unit, self._coins.get(unit, 0))
            remain -= unit * count
        return remain == 0

    # ── 거스름돈 지급 ───────────────────────────────────────────
    def give_change(self, amount: int) -> ChangeStack | None:
        """
        거스름돈 지급.
        성공 시 ChangeStack 반환하고 보유고 차감.
        잔돈 부족 시 None 반환 (보유고 변경 없음).
        """
        if amount == 0:
            return ChangeStack()
        if not self.can_make_change(amount):
            return None
        stack  = ChangeStack()
        remain = amount
        for unit in RESERVE_DENOMS:
            count = min(remain // unit, self._coins.get(unit, 0))
            if count > 0:
                self._coins[unit] -= count
                remain -= unit * count
                stack.push(unit, count)
        return stack

    # ── 투입 동전 편입 ──────────────────────────────────────────
    def accept_coins(self, coin) -> None:
        """고객이 투입한 동전(CoinSlot)을 보유고에 추가."""
        for unit in VALID_UNITS:
            idx      = UNIT_INDEX[unit]
            inserted = coin.contents.slot[idx]
            if inserted > 0:
                self._coins[unit] = self._coins.get(unit, 0) + inserted

    # ── 수금 ────────────────────────────────────────────────────
    def collect(self, min_keep: int = MIN_RESERVE) -> int:
        """
        수금: 각 거스름돈 단위는 min_keep개 이상 남기고 나머지 수거.
        1000원권은 전액 수거.
        수거된 총 금액(원) 반환.
        """
        collected = 0
        for unit in RESERVE_DENOMS:
            available = max(0, self._coins.get(unit, 0) - min_keep)
            self._coins[unit] -= available
            collected += unit * available
        # 1000원권 전액 수거
        collected += 1000 * self._coins.get(1000, 0)
        self._coins[1000] = 0
        return collected
