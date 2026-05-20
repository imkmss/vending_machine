from __future__ import annotations

import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QDialog,
    QDialogButtonBox, QSpinBox,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from client.core.beverage import Inventory
from client.core.coin_manager import ChangeReserve, MIN_RESERVE
from client.data.file_manager import (
    load_sales, load_restocks, append_restock,
    append_collection, load_collections,
)
from client.data.auth_manager import check_password, set_password

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib
    matplotlib.rcParams["font.family"] = "AppleGothic"
    _MPL = True
except ImportError:
    _MPL = False


# ── 모듈 레벨 헬퍼 ────────────────────────────────────────

def _calc_stock_from_csv(client_id: str, default_stock: int = 10) -> dict[int, int]:
    """CSV 판매·보충 기록으로 drink_id별 현재 재고 역산."""
    sold: dict[int, int] = {}
    for row in load_sales():
        if row["client_id"] == client_id:
            did = int(row["drink_id"])
            sold[did] = sold.get(did, 0) + 1

    restocked: dict[int, int] = {}
    for row in load_restocks():
        if row["client_id"] == client_id:
            did = int(row["drink_id"])
            restocked[did] = restocked.get(did, 0) + int(row["amount"])

    result: dict[int, int] = {}
    for did in range(1, 9):
        result[did] = max(0, default_stock - sold.get(did, 0) + restocked.get(did, 0))
    return result


def _load_sales_detail(client_id: str, start: int, end: int):
    """날짜 범위 내 매출을 일별·월별·음료별로 집계."""
    daily:    dict[int, int] = {}
    monthly:  dict[int, int] = {}
    by_drink: dict[str, dict] = {}

    for row in load_sales():
        if row["client_id"] != client_id:
            continue
        date_int = int(row["date"].replace("-", ""))
        if not (start <= date_int <= end):
            continue
        price = int(row["price"])
        name  = row["drink_name"]

        daily[date_int]   = daily.get(date_int, 0) + price
        monthly[date_int // 100] = monthly.get(date_int // 100, 0) + price
        if name not in by_drink:
            by_drink[name] = {"count": 0, "total": 0}
        by_drink[name]["count"] += 1
        by_drink[name]["total"] += price

    return daily, monthly, by_drink


# ── 비밀번호 다이얼로그 ────────────────────────────────────
class PasswordDialog(QDialog):
    """관리자 비밀번호 입력 다이얼로그."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("관리자 인증")
        self.setFixedSize(320, 140)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("비밀번호를 입력하세요:"))
        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.Password)
        self._edit.setPlaceholderText("초기 비밀번호: admin123!")
        self._edit.returnPressed.connect(self._try_accept)
        layout.addWidget(self._edit)

        self._lbl_err = QLabel("")
        self._lbl_err.setStyleSheet("color:red; font-size:11px;")
        layout.addWidget(self._lbl_err)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _try_accept(self):
        pw = self._edit.text()
        if check_password(pw):
            self.accept()
        else:
            self._lbl_err.setText("비밀번호가 틀렸습니다.")
            self._edit.clear()
            self._edit.setFocus()


# ── 관리자 메인 창 ────────────────────────────────────────
class AdminWindow(QMainWindow):
    """관리자 화면 — 재고 현황 / 매출 조회 / 이름 변경 / 재고 보충 / 비밀번호 변경."""

    closed = pyqtSignal()   # 창 닫힐 때 판매 화면 재활성화용

    def __init__(self, inventory: Inventory, client_id: str = "VM_01",
                 reserve: ChangeReserve | None = None):
        super().__init__()
        self.inventory = inventory
        self.client_id = client_id
        self.reserve   = reserve or ChangeReserve()

        self.setWindowTitle(f"관리자 — {client_id}")
        self.setFixedSize(740, 560)
        self._sync_stock_from_csv()
        self._init_ui()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    # ── 재고 동기화 ───────────────────────────────
    def _sync_stock_from_csv(self):
        stock_map = _calc_stock_from_csv(self.client_id)
        for node in self.inventory.to_list():
            self.inventory.set_stock(node["drink_id"], stock_map.get(node["drink_id"], node["stock"]))

    # ── UI 구성 ───────────────────────────────────
    _SIDEBAR_W   = 200
    _BTN_H       = 80
    _BG_WINDOW   = "#2b2b2b"
    _BG_SIDEBAR  = "#383838"
    _BTN_NORMAL  = "#cccccc"
    _BTN_ACTIVE  = "#e8e8e8"
    _BTN_TEXT    = "#cc2200"
    _TABLE_STYLE = (
        "QTableWidget { color: black; }"
        "QHeaderView::section { color: black; font-weight: bold;"
        " background: #e0e0e0; border: 1px solid #bbb; }"
    )

    def _init_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background:{self._BG_WINDOW};")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # 좌측 사이드바
        sidebar = QWidget()
        sidebar.setFixedWidth(self._SIDEBAR_W)
        sidebar.setStyleSheet(f"background:{self._BG_SIDEBAR}; border-radius:6px;")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(8, 8, 8, 8)
        sb_layout.setSpacing(8)

        self._tab_buttons: list[QPushButton] = []
        for i, label in enumerate(["재고 현황", "매출 조회", "이름 변경", "재고 보충", "화폐 현황", "비밀번호 변경"]):
            btn = QPushButton(label)
            btn.setFixedHeight(self._BTN_H)
            btn.setCheckable(True)
            btn.setFont(QFont("맑은 고딕", 24, QFont.Bold))
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            self._tab_buttons.append(btn)
            sb_layout.addWidget(btn)

        sb_layout.addStretch()
        root.addWidget(sidebar)

        # 우측 콘텐츠 영역
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(
            "QWidget { color: black; background: #f5f5f5; }"
            "QStackedWidget { border-radius: 6px; }"
        )
        self._stack.addWidget(self._build_inventory_tab())
        self._stack.addWidget(self._build_sales_tab())
        self._stack.addWidget(self._build_rename_tab())
        self._stack.addWidget(self._build_restock_tab())
        self._stack.addWidget(self._build_coin_tab())
        self._stack.addWidget(self._build_password_tab())
        root.addWidget(self._stack)

        self._switch_tab(0)

    def _switch_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_buttons):
            active = i == idx
            btn.setChecked(active)
            bg = self._BTN_ACTIVE if active else self._BTN_NORMAL
            btn.setStyleSheet(
                f"QPushButton {{ background:{bg}; color:{self._BTN_TEXT};"
                f" border-radius:8px; font-size:26px; font-weight:bold; }}"
            )

    # ── 탭 1: 재고 현황 ───────────────────────────
    def _build_inventory_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)

        self._inv_table = QTableWidget(0, 4)
        self._inv_table.setHorizontalHeaderLabels(["ID", "음료 이름", "가격(원)", "재고"])
        self._inv_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._inv_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._inv_table.setAlternatingRowColors(True)
        self._inv_table.setStyleSheet(self._TABLE_STYLE)
        layout.addWidget(self._inv_table)

        btn_refresh = QPushButton("새로고침")
        btn_refresh.setFixedHeight(34)
        btn_refresh.setStyleSheet("background:#1976D2; color:white; border-radius:6px; font-size:13px;")
        btn_refresh.clicked.connect(self._refresh_inventory)
        layout.addWidget(btn_refresh)

        self._refresh_inventory()
        return w

    def _refresh_inventory(self):
        self._sync_stock_from_csv()
        nodes = self.inventory.to_list()
        self._inv_table.setRowCount(len(nodes))
        for r, node in enumerate(nodes):
            self._inv_table.setItem(r, 0, QTableWidgetItem(str(node["drink_id"])))
            self._inv_table.setItem(r, 1, QTableWidgetItem(node["name"]))
            self._inv_table.setItem(r, 2, QTableWidgetItem(f"{node['price']:,}"))
            item = QTableWidgetItem(str(node["stock"]))
            item.setForeground(Qt.red if node["stock"] < 3 else Qt.black)
            self._inv_table.setItem(r, 3, item)

    # ── 탭 2: 매출 조회 ───────────────────────────
    def _build_sales_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        today  = datetime.date.today()
        years  = [str(y) for y in range(2024, today.year + 3)]
        months = [f"{m:02d}" for m in range(1, 13)]
        days   = [f"{d:02d}" for d in range(1, 32)]

        def make_date_row(label: str, default: datetime.date):
            row = QHBoxLayout()
            row.setSpacing(4)
            row.addWidget(QLabel(label))
            cb_y = QComboBox(); cb_y.addItems(years); cb_y.setCurrentText(str(default.year))
            cb_m = QComboBox(); cb_m.addItems(months); cb_m.setCurrentText(f"{default.month:02d}")
            cb_d = QComboBox(); cb_d.addItems(days);   cb_d.setCurrentText(f"{default.day:02d}")
            for cb in (cb_y, cb_m, cb_d):
                cb.setFixedWidth(70)
            row.addWidget(cb_y); row.addWidget(QLabel("년"))
            row.addWidget(cb_m); row.addWidget(QLabel("월"))
            row.addWidget(cb_d); row.addWidget(QLabel("일"))
            row.addStretch()
            return row, cb_y, cb_m, cb_d

        start_row, self._cb_sy, self._cb_sm, self._cb_sd = make_date_row(
            "시작일:", datetime.date(today.year, 1, 1)
        )
        end_row,   self._cb_ey, self._cb_em, self._cb_ed = make_date_row(
            "종료일:", today
        )
        layout.addLayout(start_row)
        layout.addLayout(end_row)

        # 일별 / 월별 토글 + 조회 버튼
        btn_row = QHBoxLayout()
        self._btn_daily   = QPushButton("일별")
        self._btn_monthly = QPushButton("월별")
        for btn in (self._btn_daily, self._btn_monthly):
            btn.setCheckable(True)
            btn.setFixedWidth(54)
            btn.setStyleSheet(
                "QPushButton { background:#E0E0E0; color:black; border-radius:4px; font-size:12px; }"
                "QPushButton:checked { background:#1976D2; color:white; }"
            )
        self._btn_daily.setChecked(True)
        self._btn_daily.clicked.connect(lambda: self._set_chart_mode("daily"))
        self._btn_monthly.clicked.connect(lambda: self._set_chart_mode("monthly"))
        btn_query = QPushButton("조회")
        btn_query.setFixedWidth(60)
        btn_query.setStyleSheet("background:#388E3C; color:white; border-radius:6px; font-size:13px;")
        btn_query.clicked.connect(self._query_sales)
        btn_row.addWidget(self._btn_daily)
        btn_row.addWidget(self._btn_monthly)
        btn_row.addWidget(btn_query)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 합계 라벨 + 수금 버튼
        total_row = QHBoxLayout()
        self._lbl_sales_total = QLabel("합계: 0 원")
        self._lbl_sales_total.setFont(QFont("맑은 고딕", 12, QFont.Bold))
        total_row.addWidget(self._lbl_sales_total)

        self._btn_collect = QPushButton("수금")
        self._btn_collect.setFixedSize(64, 30)
        self._btn_collect.setStyleSheet(
            "background:#E53935; color:white; border-radius:6px; font-size:13px; font-weight:bold;"
        )
        self._btn_collect.setVisible(False)
        self._btn_collect.clicked.connect(self._on_collect)
        total_row.addWidget(self._btn_collect)
        total_row.addStretch()
        layout.addLayout(total_row)

        # 음료별 매출 테이블
        self._drink_table = QTableWidget(0, 3)
        self._drink_table.setHorizontalHeaderLabels(["음료명", "판매 수", "매출액(원)"])
        self._drink_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._drink_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._drink_table.setAlternatingRowColors(True)
        self._drink_table.setFixedHeight(160)
        self._drink_table.setStyleSheet(self._TABLE_STYLE)
        layout.addWidget(self._drink_table)

        # 차트
        if _MPL:
            self._fig    = Figure(figsize=(6, 2.5), tight_layout=True)
            self._canvas = FigureCanvas(self._fig)
            layout.addWidget(self._canvas)
        else:
            layout.addWidget(QLabel("matplotlib 미설치 — 차트 비활성"))

        self._chart_mode = "daily"
        self._last_daily:   dict[int, int] = {}
        self._last_monthly: dict[int, int] = {}
        return w

    def _set_chart_mode(self, mode: str):
        self._chart_mode = mode
        self._btn_daily.setChecked(mode == "daily")
        self._btn_monthly.setChecked(mode == "monthly")
        self._draw_chart()

    def _query_sales(self):
        start = int(self._cb_sy.currentText() + self._cb_sm.currentText() + self._cb_sd.currentText())
        end   = int(self._cb_ey.currentText() + self._cb_em.currentText() + self._cb_ed.currentText())
        if start > end:
            QMessageBox.warning(self, "입력 오류", "시작일이 종료일보다 늦습니다.")
            return

        daily, monthly, by_drink = _load_sales_detail(self.client_id, start, end)
        self._last_daily   = daily
        self._last_monthly = monthly
        self._last_start   = start
        self._last_end     = end

        total = sum(daily.values())
        self._last_total = total
        self._lbl_sales_total.setText(f"합계: {total:,} 원")
        self._btn_collect.setVisible(total > 0)

        # 음료별 테이블 채우기
        rows = sorted(by_drink.items(), key=lambda x: -x[1]["total"])
        self._drink_table.setRowCount(len(rows))
        for r, (name, data) in enumerate(rows):
            self._drink_table.setItem(r, 0, QTableWidgetItem(name))
            self._drink_table.setItem(r, 1, QTableWidgetItem(str(data["count"])))
            self._drink_table.setItem(r, 2, QTableWidgetItem(f"{data['total']:,}"))

        self._draw_chart()

    def _on_collect(self):
        start_str = str(self._last_start)
        end_str   = str(self._last_end)
        for row in load_collections():
            if (row["client_id"] == self.client_id
                    and row["start_date"] == start_str
                    and row["end_date"]   == end_str
                    and row["mode"]       == self._chart_mode):
                QMessageBox.warning(
                    self, "수금 불가",
                    f"이미 수금된 기록이 있습니다.\n"
                    f"(수금일: {row['collected_at']}, {row['amount']}원)"
                )
                return

        append_collection(
            collected_at=datetime.date.today().isoformat(),
            client_id=self.client_id,
            start_date=start_str,
            end_date=end_str,
            mode=self._chart_mode,
            amount=self._last_total,
        )
        self._btn_collect.setVisible(False)
        QMessageBox.information(self, "수금 완료", f"{self._last_total:,} 원 수금이 기록되었습니다.")

    def _draw_chart(self):
        if not _MPL:
            return
        data = self._last_daily if self._chart_mode == "daily" else self._last_monthly
        if not data:
            return

        labels = [str(k) for k in sorted(data)]
        values = [data[k] for k in sorted(data)]

        self._fig.clear()
        ax = self._fig.add_subplot(111)
        bars = ax.bar(labels, values, color="#42A5F5")
        ax.set_xlabel("날짜" if self._chart_mode == "daily" else "월")
        ax.set_ylabel("매출(원)")
        ax.set_title(f"{self.client_id} {'일별' if self._chart_mode == 'daily' else '월별'} 매출")
        ax.tick_params(axis="x", rotation=30)
        if values:
            for bar, val in zip(bars, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.01,
                    f"{val:,}", ha="center", va="bottom", fontsize=8,
                )
        self._canvas.draw()

    # ── 탭 3: 이름 변경 ───────────────────────────
    def _build_rename_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.addWidget(QLabel("음료 ID (1~8):"), 0, 0)
        self._edit_drink_id = QLineEdit()
        self._edit_drink_id.setPlaceholderText("예: 3")
        grid.addWidget(self._edit_drink_id, 0, 1)
        grid.addWidget(QLabel("새 이름:"), 1, 0)
        self._edit_new_name = QLineEdit()
        self._edit_new_name.setPlaceholderText("예: 탄산수")
        grid.addWidget(self._edit_new_name, 1, 1)
        layout.addLayout(grid)

        btn = QPushButton("이름 변경")
        btn.setFixedHeight(40)
        btn.setStyleSheet("background:#F57C00; color:white; border-radius:8px; font-size:13px; font-weight:bold;")
        btn.clicked.connect(self._on_rename)
        layout.addWidget(btn)

        self._lbl_rename_result = QLabel("")
        self._lbl_rename_result.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._lbl_rename_result)
        layout.addStretch()
        return w

    def _on_rename(self):
        try:
            drink_id = int(self._edit_drink_id.text().strip())
        except ValueError:
            self._lbl_rename_result.setText("유효한 음료 ID를 입력하세요.")
            return
        new_name = self._edit_new_name.text().strip()
        if not new_name:
            self._lbl_rename_result.setText("새 이름을 입력하세요.")
            return
        node = self.inventory.find(drink_id)
        if node is None:
            self._lbl_rename_result.setText("해당 음료를 찾을 수 없습니다.")
            return
        old_name = node.name
        self.inventory.rename(drink_id, new_name)
        self._lbl_rename_result.setStyleSheet("color: green;")
        self._lbl_rename_result.setText(f"'{old_name}' → '{new_name}' 변경 완료")
        self._refresh_inventory()

    # ── 탭 4: 재고 보충 ───────────────────────────
    def _build_restock_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(12)

        layout.addWidget(QLabel("음료를 선택하고 보충할 수량을 입력하세요."))

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.addWidget(QLabel("음료 ID (1~8):"), 0, 0)
        self._edit_restock_id = QLineEdit()
        self._edit_restock_id.setPlaceholderText("예: 2")
        grid.addWidget(self._edit_restock_id, 0, 1)

        grid.addWidget(QLabel("보충 수량:"), 1, 0)
        self._spin_amount = QSpinBox()
        self._spin_amount.setRange(1, 10)
        self._spin_amount.setValue(1)
        grid.addWidget(self._spin_amount, 1, 1)
        layout.addLayout(grid)

        btn = QPushButton("재고 보충")
        btn.setFixedHeight(40)
        btn.setStyleSheet("background:#00897B; color:white; border-radius:8px; font-size:13px; font-weight:bold;")
        btn.clicked.connect(self._on_restock)
        layout.addWidget(btn)

        self._lbl_restock_result = QLabel("")
        self._lbl_restock_result.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._lbl_restock_result)
        layout.addStretch()
        return w

    def _on_restock(self):
        try:
            drink_id = int(self._edit_restock_id.text().strip())
        except ValueError:
            self._lbl_restock_result.setText("유효한 음료 ID를 입력하세요.")
            return

        node = self.inventory.find(drink_id)
        if node is None:
            self._lbl_restock_result.setText(f"drink_id {drink_id}를 찾을 수 없습니다.")
            return

        MAX_STOCK = 10
        current = node.stock
        if current >= MAX_STOCK:
            self._lbl_restock_result.setStyleSheet("color: red;")
            self._lbl_restock_result.setText(f"'{node.name}'은 이미 최대 재고({MAX_STOCK}개)입니다.")
            return

        amount = min(self._spin_amount.value(), MAX_STOCK - current)
        self.inventory.restock(drink_id, amount)

        append_restock(
            date_str=datetime.date.today().isoformat(),
            client_id=self.client_id,
            drink_id=drink_id,
            drink_name=node.name,
            amount=amount,
        )
        self._lbl_restock_result.setStyleSheet("color: green;")
        self._lbl_restock_result.setText(
            f"'{node.name}' {amount}개 보충 완료 (현재 재고: {node.stock}개 / {MAX_STOCK}개)"
        )
        self._refresh_inventory()

    # ── 탭 5: 화폐 현황 ──────────────────────────
    def _build_coin_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 테이블: 단위 / 보유 수량 / 금액
        self._coin_table = QTableWidget(0, 3)
        self._coin_table.setHorizontalHeaderLabels(["단위(원)", "보유 수량(개)", "금액(원)"])
        self._coin_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._coin_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._coin_table.setAlternatingRowColors(True)
        self._coin_table.setStyleSheet(self._TABLE_STYLE)
        layout.addWidget(self._coin_table)

        # 합계 레이블
        self._lbl_coin_total = QLabel("합계: 0 원")
        self._lbl_coin_total.setAlignment(Qt.AlignRight)
        self._lbl_coin_total.setFont(QFont("맑은 고딕", 13, QFont.Bold))
        self._lbl_coin_total.setStyleSheet("color: #1a237e; padding-right: 4px;")
        layout.addWidget(self._lbl_coin_total)

        # 버튼 행
        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("새로고침")
        btn_refresh.setFixedHeight(36)
        btn_refresh.setStyleSheet(
            "QPushButton { background:#1565C0; color:white; border-radius:6px; font-size:13px; }"
            "QPushButton:pressed { background:#0D47A1; }"
        )
        btn_refresh.clicked.connect(self._refresh_coin_status)

        btn_collect = QPushButton(f"수금  (각 단위 {MIN_RESERVE}개 유지)")
        btn_collect.setFixedHeight(36)
        btn_collect.setStyleSheet(
            "QPushButton { background:#E53935; color:white; border-radius:6px; font-size:13px; }"
            "QPushButton:pressed { background:#B71C1C; }"
        )
        btn_collect.clicked.connect(self._on_coin_collect)

        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_collect)
        layout.addLayout(btn_row)

        self._refresh_coin_status()
        return w

    def _refresh_coin_status(self):
        status = self.reserve.status()
        rows   = sorted(status.items(), reverse=True)   # 500 → 100 → 50 → 10 → (1000 마지막)
        rows   = [(u, c) for u, c in rows if u != 1000] + \
                 [(1000, status.get(1000, 0))]           # 1000원 맨 아래

        self._coin_table.setRowCount(len(rows))
        for r, (unit, count) in enumerate(rows):
            self._coin_table.setItem(r, 0, QTableWidgetItem(f"{unit:,}"))
            self._coin_table.setItem(r, 1, QTableWidgetItem(str(count)))
            self._coin_table.setItem(r, 2, QTableWidgetItem(f"{unit * count:,}"))
            for c in range(3):
                self._coin_table.item(r, c).setTextAlignment(Qt.AlignCenter)

        self._lbl_coin_total.setText(f"합계:  {self.reserve.total_amount():,} 원")

    def _on_coin_collect(self):
        preview = self.reserve.total_amount()
        if preview == 0:
            QMessageBox.information(self, "수금", "수금할 금액이 없습니다.")
            return
        collected = self.reserve.collect()
        self._refresh_coin_status()
        QMessageBox.information(
            self, "수금 완료",
            f"{collected:,} 원을 수금했습니다.\n(각 단위 {MIN_RESERVE}개 유지)"
        )

    # ── 탭 6: 비밀번호 변경 ───────────────────────
    def _build_password_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(QLabel("비밀번호 조건: 8자리 이상, 숫자 1개 이상, 특수문자 1개 이상"))

        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(QLabel("현재 비밀번호:"), 0, 0)
        self._edit_cur_pw = QLineEdit()
        self._edit_cur_pw.setEchoMode(QLineEdit.Password)
        grid.addWidget(self._edit_cur_pw, 0, 1)

        grid.addWidget(QLabel("새 비밀번호:"), 1, 0)
        self._edit_new_pw = QLineEdit()
        self._edit_new_pw.setEchoMode(QLineEdit.Password)
        grid.addWidget(self._edit_new_pw, 1, 1)

        grid.addWidget(QLabel("새 비밀번호 확인:"), 2, 0)
        self._edit_new_pw2 = QLineEdit()
        self._edit_new_pw2.setEchoMode(QLineEdit.Password)
        grid.addWidget(self._edit_new_pw2, 2, 1)

        layout.addLayout(grid)

        btn = QPushButton("비밀번호 변경")
        btn.setFixedHeight(40)
        btn.setStyleSheet("background:#5C6BC0; color:white; border-radius:8px; font-size:13px; font-weight:bold;")
        btn.clicked.connect(self._on_change_password)
        layout.addWidget(btn)

        self._lbl_pw_result = QLabel("")
        self._lbl_pw_result.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._lbl_pw_result)
        layout.addStretch()
        return w

    def _on_change_password(self):
        cur  = self._edit_cur_pw.text()
        new1 = self._edit_new_pw.text()
        new2 = self._edit_new_pw2.text()

        if not check_password(cur):
            self._lbl_pw_result.setStyleSheet("color:red;")
            self._lbl_pw_result.setText("현재 비밀번호가 올바르지 않습니다.")
            return
        if new1 != new2:
            self._lbl_pw_result.setStyleSheet("color:red;")
            self._lbl_pw_result.setText("새 비밀번호가 일치하지 않습니다.")
            return

        ok, msg = set_password(new1)
        if ok:
            self._lbl_pw_result.setStyleSheet("color:green;")
            for edit in (self._edit_cur_pw, self._edit_new_pw, self._edit_new_pw2):
                edit.clear()
        else:
            self._lbl_pw_result.setStyleSheet("color:red;")
        self._lbl_pw_result.setText(msg)
