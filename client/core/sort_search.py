from __future__ import annotations

from client.core.beverage import DrinkNode, Inventory


# ======================================================================
# 정렬
# ======================================================================

def selection_sort_by_price(drinks: list[DrinkNode]) -> list[DrinkNode]:
    """
    선택 정렬 — 가격 오름차순.
    구매 가능 음료 표시 시 사용.  O(n²)
    """
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
    """
    퀵 정렬 — 판매량(sold) 내림차순.
    관리자 화면 인기 음료 순위에 사용.  O(n log n) avg
    각 dict는 {"drink_id", "name", "price", "sold"} 형식이어야 함.
    """
    if len(drinks) <= 1:
        return drinks

    pivot = drinks[len(drinks) // 2]["sold"]
    left   = [d for d in drinks if d["sold"] > pivot]   # 판매량 높은 쪽
    middle = [d for d in drinks if d["sold"] == pivot]
    right  = [d for d in drinks if d["sold"] < pivot]

    return quick_sort_by_sales(left) + middle + quick_sort_by_sales(right)


# ======================================================================
# 탐색
# ======================================================================

def linear_search(inventory: Inventory, drink_id: int) -> DrinkNode | None:
    """
    선형 탐색 — 재고 Linked List에서 drink_id 음료 찾기.
    Inventory.find()의 독립 함수 버전.  O(n)
    """
    cur = inventory.head
    while cur:
        if cur.drink_id == drink_id:
            return cur
        cur = cur.next
    return None


def binary_search_sales(sorted_nodes: list, date: int):
    """
    이진 탐색 — 날짜(YYYYMMDD) 기준으로 매출 노드 찾기.
    sorted_nodes는 inorder() 결과처럼 날짜 오름차순 정렬된 리스트.
    O(log n)
    """
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
