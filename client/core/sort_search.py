"""재고·매출 데이터에 적용하는 정렬 및 탐색 알고리즘 모음."""
from __future__ import annotations

from client.core.beverage import DrinkNode, Inventory


# ── 정렬 ──────────────────────────────────────────────────────────

def selection_sort_by_price(drinks: list[DrinkNode]) -> list[DrinkNode]:
    """선택 정렬: 음료 목록을 가격 오름차순으로 정렬한다."""
    arr = drinks[:]
    n = len(arr)
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            if arr[j].price < arr[min_idx].price:
                min_idx = j
        arr[i], arr[min_idx] = arr[min_idx], arr[i]
    return arr


def quick_sort_by_sales(drinks: list[dict]) -> list[dict]:
    """퀵 정렬: 음료 목록을 판매량(sold) 내림차순으로 정렬한다."""
    if len(drinks) <= 1:
        return drinks

    pivot  = drinks[len(drinks) // 2]["sold"]
    left   = [d for d in drinks if d["sold"] > pivot]   # 판매량 높은 쪽
    middle = [d for d in drinks if d["sold"] == pivot]
    right  = [d for d in drinks if d["sold"] < pivot]

    return quick_sort_by_sales(left) + middle + quick_sort_by_sales(right)


# ── 탐색 ──────────────────────────────────────────────────────────

def linear_search(inventory: Inventory, drink_id: int) -> DrinkNode | None:
    """선형 탐색: Linked-List에서 drink_id에 해당하는 노드를 검색한다."""
    cur = inventory.head
    while cur:
        if cur.drink_id == drink_id:
            return cur
        cur = cur.next
    return None


def binary_search_sales(sorted_nodes: list, date: int):
    """이진 탐색: 날짜 오름차순으로 정렬된 매출 노드 배열에서 특정 날짜를 검색한다."""
    lo, hi = 0, len(sorted_nodes) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if sorted_nodes[mid].date == date:
            return sorted_nodes[mid]
        elif sorted_nodes[mid].date < date:
            lo = mid + 1
        else:
            hi = mid - 1
    return None
