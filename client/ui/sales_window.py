from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QTextEdit, QFrame,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap

_IMAGES_DIR = Path(__file__).parent.parent / "images"

def _load_pixmap(name: str) -> QPixmap | None:
    for ext in ("png", "jpg", "jpeg"):
        p = _IMAGES_DIR / f"{name}.{ext}"
        if p.exists():
            return QPixmap(str(p))
    return None

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
    clicked = pyqtSignal(int)

    _BG_NORMAL   = "#2C2C2C"
    _BG_DISABLED = "#3A3A3A"
    _BG_PRICE    = "#1A1A1A"
    _BG_IMG      = "#444444"

    def __init__(self, drink_id: int, name: str, price: int, parent=None):
        super().__init__(parent)
        self.drink_id      = drink_id
        self._name         = name
        self._price        = price
        self._enabled_flag = True

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"QFrame {{ background:{self._BG_NORMAL}; border-radius:6px; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 이미지 영역
        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignCenter)
        self._img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._img_label.setStyleSheet("background:transparent;")
        self._pixmap = _load_pixmap(name)
        if not self._pixmap:
            self._img_label.setStyleSheet(f"background:{self._BG_IMG}; border-radius:4px;")
        outer.addWidget(self._img_label, stretch=1)

        # 하단 바: 이름(좌) + 가격(우)
        price_bar = QWidget()
        price_bar.setFixedHeight(26)
        price_bar.setStyleSheet(
            f"background:{self._BG_PRICE};"
            "border-bottom-left-radius:6px; border-bottom-right-radius:6px;"
        )
        bar_layout = QHBoxLayout(price_bar)
        bar_layout.setContentsMargins(6, 0, 6, 0)
        bar_layout.setSpacing(4)

        self._lbl_name = QLabel(name)
        self._lbl_name.setStyleSheet(
            "color:white; font-size:11px; font-weight:bold; background:transparent;"
        )
        self._lbl_name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._lbl_price = QLabel(f"{price:,}")
        self._lbl_price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._lbl_price.setStyleSheet(
            "color:#FFD54F; font-size:11px; background:transparent;"
        )
        self._lbl_price.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)

        bar_layout.addWidget(self._lbl_name)
        bar_layout.addWidget(self._lbl_price)
        outer.addWidget(price_bar)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap and not self._pixmap.isNull():
            size = self._img_label.size()
            if size.width() > 0 and size.height() > 0:
                scaled = self._pixmap.scaled(
                    size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                self._img_label.setPixmap(scaled)

    def mousePressEvent(self, event):
        if self._enabled_flag and event.button() == Qt.LeftButton:
            self.clicked.emit(self.drink_id)

    def set_active(self, name: str, purchasable: bool = False):
        self._enabled_flag = True
        self.setCursor(Qt.PointingHandCursor)
        bg = "#FFFFFF" if purchasable else self._BG_NORMAL
        self.setStyleSheet(f"QFrame {{ background:{bg}; border-radius:6px; }}")
        self._lbl_name.setText(name)
        color = "#22FF33" if purchasable else "white"
        self._lbl_name.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:bold; background:transparent;"
        )

    def set_disabled_style(self, name: str):
        self._enabled_flag = False
        self.setCursor(Qt.ArrowCursor)
        self.setStyleSheet(f"QFrame {{ background:{self._BG_DISABLED}; border-radius:6px; }}")
        self._lbl_name.setText(name)
        self._lbl_name.setStyleSheet(
            "color:#666; font-size:11px; font-weight:bold; background:transparent;"
        )

    def set_soldout(self, name: str):
        self._enabled_flag = False
        self.setCursor(Qt.ArrowCursor)
        self.setStyleSheet(f"QFrame {{ background:{self._BG_DISABLED}; border-radius:6px; }}")
        self._lbl_name.setText(f"{name} [품절]")
        self._lbl_name.setStyleSheet(
            "color:#666; font-size:11px; font-weight:bold; background:transparent;"
        )


class SalesWindow(QMainWindow):
    """고객용 자판기 화면 — 3:4 비율 (600×800)."""

    def __init__(self, client_id: str = "VM_01"):
        super().__init__()
        self.client_id = client_id
        self.setWindowTitle(f"자판기 — {client_id}")
        self.setFixedSize(450, 595)

        self.inventory  = Inventory()
        self.send_queue = SendQueue()
        self.session    = VendingSession(client_id, self.inventory, self.send_queue)

        from datetime import date
        self.session.daily_sales = get_daily_total(client_id, date.today().isoformat())

        self._init_ui()
        self._refresh_drinks()

    # ── UI 구성 ───────────────────────────────
    def _init_ui(self):
        central = QWidget()
        central.setStyleSheet("background:#ECEFF1;")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 10)

        # ── 1. 음료 버튼 그리드 ───────────────
        drink_frame = QFrame()
        drink_frame.setStyleSheet("background:#ECEFF1;")
        drink_grid = QGridLayout(drink_frame)
        drink_grid.setSpacing(8)
        drink_grid.setContentsMargins(16, 16, 16, 3)

        self._drink_btns: dict[int, DrinkButton] = {}
        for i, node in enumerate(self.inventory.to_list()):
            btn = DrinkButton(node["drink_id"], node["name"], node["price"])
            btn.clicked.connect(self._on_select)
            drink_grid.addWidget(btn, i // 3, i % 3)
            self._drink_btns[node["drink_id"]] = btn

        # 9번째 더미 슬롯 (기능 없음, 이미지 표시)
        dummy = QLabel()
        dummy.setAlignment(Qt.AlignCenter)
        dummy.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        dummy.setStyleSheet("background:#D9D9D9; border-radius:6px;")
        dummy_pixmap = QPixmap(str(_IMAGES_DIR / "image.png"))
        if not dummy_pixmap.isNull():
            dummy.setPixmap(
                dummy_pixmap.scaled(130, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        drink_grid.addWidget(dummy, 2, 2)

        root.addWidget(drink_frame, stretch=5)

        # ── 2. 화폐 투입 + 반환 + 금액 표시 ──
        coin_widget = QWidget()
        coin_widget.setStyleSheet("background:#ECEFF1;")
        coin_layout = QVBoxLayout(coin_widget)
        coin_layout.setContentsMargins(16, 3, 16, 10)
        coin_layout.setSpacing(10)

        # 화폐 버튼 행
        coin_row = QHBoxLayout()
        coin_row.setSpacing(8)
        for unit in COIN_UNITS:
            btn = QPushButton(f"{unit:,}원")
            btn.setFixedHeight(44)
            btn.setStyleSheet(
                "QPushButton { background:#FF8D28; color:white; border-radius:6px;"
                " font-size:13px; font-weight:bold; }"
                "QPushButton:pressed { background:#E07010; }"
            )
            btn.clicked.connect(lambda _, u=unit: self._on_insert(u))
            coin_row.addWidget(btn)
        coin_layout.addLayout(coin_row)

        # 반환 버튼(6.5) + 금액 표시(3.5)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        btn_refund = QPushButton("반 환")
        btn_refund.setFixedHeight(44)
        btn_refund.setStyleSheet(
            "QPushButton { background:#E53935; color:white; border-radius:8px;"
            " font-size:14px; font-weight:bold; }"
            "QPushButton:pressed { background:#B71C1C; }"
        )
        btn_refund.clicked.connect(self._on_refund)
        btn_refund.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._lbl_total = QLabel("0 원")
        self._lbl_total.setAlignment(Qt.AlignCenter)
        self._lbl_total.setFont(QFont("맑은 고딕", 16, QFont.Bold))
        self._lbl_total.setStyleSheet(
            "color:#FFD54F; background:#1A2A30; border-radius:8px;"
        )
        self._lbl_total.setFixedHeight(44)
        self._lbl_total.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        bottom_row.addWidget(btn_refund, 65)
        bottom_row.addWidget(self._lbl_total, 35)
        coin_layout.addLayout(bottom_row)

        root.addWidget(coin_widget, stretch=2)

        # ── 3. 거스름돈 표시 ─────────────────
        change_widget = QWidget()
        change_widget.setStyleSheet("background:#ECEFF1;")
        change_widget.setFixedHeight(80)
        change_layout = QVBoxLayout(change_widget)
        change_layout.setContentsMargins(12, 0, 12, 4)
        change_layout.setSpacing(2)

        self._txt_change = QTextEdit()
        self._txt_change.setReadOnly(True)
        self._txt_change.setStyleSheet(
            "background:white; border-radius:6px; font-size:12px; padding:4px; color:black;"
        )
        self._txt_change.setPlaceholderText("화폐를 투입하세요.")
        change_layout.addWidget(self._txt_change)

        root.addWidget(change_widget)

    # ── 이벤트 핸들러 ─────────────────────────
    def _on_insert(self, amount: int):
        result = self.session.insert_coin(amount)
        if result == OK:
            self._lbl_total.setText(f"{self.session.total:,} 원")
            self._txt_change.setPlainText(f"{amount:,}원 투입되었습니다.")
            self._refresh_drinks()
        else:
            self._txt_change.setPlainText(_INSERT_MSG.get(result, "투입 오류"))

    def _on_select(self, drink_id: int):
        ok, change_stack, msg = self.session.select_drink(drink_id)

        if ok:
            rec = self.send_queue.peek()
            if rec:
                append_sale(
                    rec.date, rec.client_id,
                    rec.sold_drink["drink_id"], rec.sold_drink["name"],
                    rec.sold_drink["price"], rec.daily_sales,
                )
            self._lbl_total.setText("0 원")
            self._show_change(change_stack, header=msg)
            self._refresh_drinks()
        else:
            self._txt_change.setPlainText(msg)

    def _on_refund(self):
        change_stack = self.session.refund()
        if change_stack is None:
            self._txt_change.setPlainText("투입된 금액이 없습니다.")
            return
        self._lbl_total.setText("0 원")
        self._show_change(change_stack, header="금액이 반환되었습니다.")
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
                btn.set_active(node["name"], purchasable=True)
            else:
                btn.set_disabled_style(node["name"])

    # ── 거스름돈 출력 ─────────────────────────
    def _show_change(self, change_stack, header: str = ""):
        lines = [header] if header else []
        if change_stack is None or change_stack.is_empty():
            lines.append("거스름돈 없음")
        else:
            lines.append("[ 거스름돈 ]")
            while not change_stack.is_empty():
                unit, count = change_stack.pop()
                lines.append(f"  {unit:>5,}원  ×  {count}개")
        self._txt_change.setPlainText("\n".join(lines))
