from __future__ import annotations

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QTextEdit, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from client.core.beverage import Inventory
from client.core.transaction import SendQueue, VendingSession
from client.core.coin_manager import OK, INVALID_UNIT, BILL_LIMIT, TOTAL_LIMIT
from client.data.file_manager import append_sale, get_daily_total

_INSERT_MSG = {
    INVALID_UNIT: "사용할 수 없는 화폐 단위입니다.",
    BILL_LIMIT:   "지폐는 최대 5,000원까지 투입 가능합니다.",
    TOTAL_LIMIT:  "최대 투입 금액(7,000원)을 초과합니다.",
}

COIN_UNITS = [10, 50, 100, 500, 1000]

# ── 커스텀 음료 버튼 ───────────────────────────
class DrinkButton(QFrame):
    """
    스크린샷 스타일 음료 버튼.
    - 어두운 배경, 좌상단 ID, 중앙 음료명, 하단 가격 띠
    """
    clicked = pyqtSignal(int)   # drink_id 전달

    _BG_NORMAL   = "#2C2C2C"
    _BG_DISABLED = "#3A3A3A"
    _BG_PRICE    = "#1A1A1A"

    def __init__(self, drink_id: int, name: str, price: int, parent=None):
        super().__init__(parent)
        self.drink_id  = drink_id
        self._enabled_flag = True
        self.setFixedSize(130, 90)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"QFrame {{ background:{self._BG_NORMAL}; border-radius:6px; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 0)
        outer.setSpacing(0)

        # ID 배지 (좌상단)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        self._lbl_id = QLabel(str(drink_id))
        self._lbl_id.setStyleSheet("color:#AAAAAA; font-size:10px; background:transparent;")
        top_row.addWidget(self._lbl_id)
        top_row.addStretch()
        outer.addLayout(top_row)

        # 음료명 (중앙)
        outer.addStretch()
        self._lbl_name = QLabel(name)
        self._lbl_name.setAlignment(Qt.AlignCenter)
        self._lbl_name.setWordWrap(True)
        self._lbl_name.setStyleSheet("color:white; font-size:12px; font-weight:bold; background:transparent;")
        outer.addWidget(self._lbl_name)
        outer.addStretch()

        # 가격 띠 (하단)
        price_bar = QWidget()
        price_bar.setFixedHeight(24)
        price_bar.setStyleSheet(f"background:{self._BG_PRICE}; border-bottom-left-radius:6px; border-bottom-right-radius:6px;")
        price_layout = QHBoxLayout(price_bar)
        price_layout.setContentsMargins(0, 0, 0, 0)
        self._lbl_price = QLabel(f"{price:,}")
        self._lbl_price.setAlignment(Qt.AlignCenter)
        self._lbl_price.setStyleSheet("color:white; font-size:11px; background:transparent;")
        price_layout.addWidget(self._lbl_price)
        outer.addWidget(price_bar)

    def mousePressEvent(self, event):
        if self._enabled_flag and event.button() == Qt.LeftButton:
            self.clicked.emit(self.drink_id)

    def set_active(self, name: str):
        self._enabled_flag = True
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"QFrame {{ background:{self._BG_NORMAL}; border-radius:6px; }}")
        self._lbl_name.setText(name)
        self._lbl_name.setStyleSheet("color:white; font-size:12px; font-weight:bold; background:transparent;")

    def set_disabled_style(self, name: str):
        self._enabled_flag = False
        self.setCursor(Qt.ArrowCursor)
        self.setStyleSheet(f"QFrame {{ background:{self._BG_DISABLED}; border-radius:6px; }}")
        self._lbl_name.setText(name)
        self._lbl_name.setStyleSheet("color:#666; font-size:12px; font-weight:bold; background:transparent;")

    def set_soldout(self, name: str):
        self._enabled_flag = False
        self.setCursor(Qt.ArrowCursor)
        self.setStyleSheet(f"QFrame {{ background:{self._BG_DISABLED}; border-radius:6px; }}")
        self._lbl_name.setText(f"{name}\n[품절]")
        self._lbl_name.setStyleSheet("color:#666; font-size:12px; font-weight:bold; background:transparent;")


class SalesWindow(QMainWindow):
    """고객용 자판기 화면."""

    def __init__(self, client_id: str = "VM_01"):
        super().__init__()
        self.client_id = client_id
        self.setWindowTitle(f"자판기 — {client_id}")
        self.setFixedSize(900, 520)

        # 핵심 객체
        self.inventory  = Inventory()
        self.send_queue = SendQueue()
        self.session    = VendingSession(client_id, self.inventory, self.send_queue)

        # 재시작 시 당일 누적 매출 복원
        from datetime import date
        self.session.daily_sales = get_daily_total(client_id, date.today().isoformat())

        self._init_ui()
        self._refresh_drinks()

    # ── UI 구성 ───────────────────────────────
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # ── 상단 헤더: 투입 금액
        header = QWidget()
        header.setStyleSheet("background:#1565C0;")
        header.setFixedHeight(90)
        h_layout = QVBoxLayout(header)
        h_layout.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel("투입 금액")
        lbl_title.setFont(QFont("맑은 고딕", 12))
        lbl_title.setStyleSheet("color:white;")
        lbl_title.setAlignment(Qt.AlignCenter)

        self._lbl_total = QLabel("0 원")
        self._lbl_total.setFont(QFont("맑은 고딕", 26, QFont.Bold))
        self._lbl_total.setStyleSheet("color:#FFD54F;")
        self._lbl_total.setAlignment(Qt.AlignCenter)

        h_layout.addWidget(lbl_title)
        h_layout.addWidget(self._lbl_total)
        root_layout.addWidget(header)

        # ── 본문: 음료 패널(좌) + 우측 패널
        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(16)

        # 음료 버튼 그리드 (4열, 어두운 테마)
        drink_frame = QFrame()
        drink_frame.setStyleSheet("background:#1E1E1E; border-radius:10px;")
        drink_grid = QGridLayout(drink_frame)
        drink_grid.setSpacing(6)
        drink_grid.setContentsMargins(8, 8, 8, 8)

        self._drink_btns: dict[int, DrinkButton] = {}
        for i, node in enumerate(self.inventory.to_list()):
            btn = DrinkButton(node["drink_id"], node["name"], node["price"])
            btn.clicked.connect(self._on_select)
            drink_grid.addWidget(btn, i // 4, i % 4)
            self._drink_btns[node["drink_id"]] = btn

        body.addWidget(drink_frame)

        # ── 우측: 화폐 투입 + 반환 + 안내 + 거스름돈
        right = QVBoxLayout()
        right.setSpacing(10)

        # 화폐 버튼 행
        coin_row = QHBoxLayout()
        for unit in COIN_UNITS:
            btn = QPushButton(f"{unit:,}원")
            btn.setFixedSize(68, 40)
            btn.setStyleSheet(
                "background:#1976D2; color:white; border-radius:6px;"
                "font-size:12px; font-weight:bold;"
            )
            btn.clicked.connect(lambda _, u=unit: self._on_insert(u))
            coin_row.addWidget(btn)
        right.addLayout(coin_row)

        # 반환 버튼
        btn_refund = QPushButton("반 환")
        btn_refund.setFixedHeight(44)
        btn_refund.setStyleSheet(
            "background:#E53935; color:white; border-radius:8px;"
            "font-size:14px; font-weight:bold;"
        )
        btn_refund.clicked.connect(self._on_refund)
        right.addWidget(btn_refund)

        # 안내 메시지
        self._lbl_msg = QLabel("화폐를 투입하세요.")
        self._lbl_msg.setWordWrap(True)
        self._lbl_msg.setStyleSheet("color:#555; font-size:12px;")
        right.addWidget(self._lbl_msg)

        # 거스름돈 출력
        self._txt_change = QTextEdit()
        self._txt_change.setReadOnly(True)
        self._txt_change.setFixedHeight(130)
        self._txt_change.setStyleSheet(
            "background:#ECEFF1; border-radius:6px; font-size:12px; padding:4px; color:black;"
        )
        self._txt_change.setPlaceholderText("거스름돈이 여기에 표시됩니다.")
        right.addWidget(self._txt_change)
        right.addStretch()

        body.addLayout(right)
        root_layout.addLayout(body)

    # ── 이벤트 핸들러 ─────────────────────────
    def _on_insert(self, amount: int):
        result = self.session.insert_coin(amount)
        if result == OK:
            self._lbl_total.setText(f"{self.session.total:,} 원")
            self._lbl_msg.setText(f"{amount:,}원 투입되었습니다.")
            self._refresh_drinks()
        else:
            self._lbl_msg.setText(_INSERT_MSG.get(result, "투입 오류"))

    def _on_select(self, drink_id: int):
        ok, change_stack, msg = self.session.select_drink(drink_id)
        self._lbl_msg.setText(msg)

        if ok:
            # 로컬 CSV 백업
            rec = self.send_queue.peek()
            if rec:
                append_sale(
                    rec.date, rec.client_id,
                    rec.sold_drink["drink_id"], rec.sold_drink["name"],
                    rec.sold_drink["price"], rec.daily_sales,
                )
            self._lbl_total.setText("0 원")
            self._show_change(change_stack)
            self._refresh_drinks()

    def _on_refund(self):
        change_stack = self.session.refund()
        if change_stack is None:
            self._lbl_msg.setText("투입된 금액이 없습니다.")
            return
        self._lbl_total.setText("0 원")
        self._lbl_msg.setText("금액이 반환되었습니다.")
        self._show_change(change_stack)
        self._refresh_drinks()

    # ── 음료 버튼 상태 갱신 ───────────────────
    def _refresh_drinks(self):
        available = {n.drink_id for n in self.session.available_drinks()}
        for node in self.inventory.to_list():
            did = node["drink_id"]
            btn = self._drink_btns[did]
            if node["stock"] == 0:
                btn.set_soldout(node["name"])
            elif did in available:
                btn.set_active(node["name"])
            else:
                btn.set_disabled_style(node["name"])

    # ── 거스름돈 출력 ─────────────────────────
    def _show_change(self, change_stack):
        self._txt_change.clear()
        if change_stack is None or change_stack.is_empty():
            self._txt_change.setPlainText("거스름돈 없음")
            return
        lines = ["[ 거스름돈 ]"]
        while not change_stack.is_empty():
            unit, count = change_stack.pop()
            lines.append(f"  {unit:>5,}원  ×  {count}개")
        self._txt_change.setPlainText("\n".join(lines))
