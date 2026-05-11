from __future__ import annotations

import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QDialog,
    QDialogButtonBox, QSpinBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from client.core.beverage import Inventory
from client.data.file_manager import load_sales, load_restocks, append_restock
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

    def __init__(self, inventory: Inventory, client_id: str = "VM_01"):
        super().__init__()
        self.inventory = inventory
        self.client_id = client_id

        self.setWindowTitle(f"관리자 — {client_id}")
        self.setFixedSize(740, 560)
        self._sync_stock_from_csv()
        self._init_ui()

    # ── 재고 동기화 ───────────────────────────────
    def _sync_stock_from_csv(self):
        stock_map = _calc_stock_from_csv(self.client_id)
        for node in self.inventory.to_list():
            self.inventory.set_stock(node["drink_id"], stock_map.get(node["drink_id"], node["stock"]))

    # ── UI 구성 ───────────────────────────────────
    def _init_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(self._build_inventory_tab(),  "재고 현황")
        tabs.addTab(self._build_sales_tab(),      "매출 조회")
        tabs.addTab(self._build_rename_tab(),     "이름 변경")
        tabs.addTab(self._build_restock_tab(),    "재고 보충")
        tabs.addTab(self._build_password_tab(),   "비밀번호 변경")

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

        # 날짜 범위 + 조회 버튼
        form = QHBoxLayout()
        form.addWidget(QLabel("시작일 (YYYYMMDD):"))
        self._edit_start = QLineEdit()
        self._edit_start.setPlaceholderText("20260101")
        form.addWidget(self._edit_start)
        form.addWidget(QLabel("종료일:"))
        self._edit_end = QLineEdit()
        self._edit_end.setPlaceholderText("20261231")
        form.addWidget(self._edit_end)

        # 일별 / 월별 토글
        self._btn_daily   = QPushButton("일별")
        self._btn_monthly = QPushButton("월별")
        for btn in (self._btn_daily, self._btn_monthly):
            btn.setCheckable(True)
            btn.setFixedWidth(54)
            btn.setStyleSheet(
                "QPushButton { background:#E0E0E0; border-radius:4px; font-size:12px; }"
                "QPushButton:checked { background:#1976D2; color:white; }"
            )
        self._btn_daily.setChecked(True)
        self._btn_daily.clicked.connect(lambda: self._set_chart_mode("daily"))
        self._btn_monthly.clicked.connect(lambda: self._set_chart_mode("monthly"))
        form.addWidget(self._btn_daily)
        form.addWidget(self._btn_monthly)

        btn_query = QPushButton("조회")
        btn_query.setFixedWidth(60)
        btn_query.setStyleSheet("background:#388E3C; color:white; border-radius:6px; font-size:13px;")
        btn_query.clicked.connect(self._query_sales)
        form.addWidget(btn_query)
        layout.addLayout(form)

        # 합계 라벨
        self._lbl_sales_total = QLabel("합계: 0 원")
        self._lbl_sales_total.setFont(QFont("맑은 고딕", 12, QFont.Bold))
        layout.addWidget(self._lbl_sales_total)

        # 음료별 매출 테이블
        self._drink_table = QTableWidget(0, 3)
        self._drink_table.setHorizontalHeaderLabels(["음료명", "판매 수", "매출액(원)"])
        self._drink_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._drink_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._drink_table.setAlternatingRowColors(True)
        self._drink_table.setFixedHeight(160)
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
        try:
            start = int(self._edit_start.text().strip())
            end   = int(self._edit_end.text().strip())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "날짜를 YYYYMMDD 형식으로 입력하세요.")
            return

        daily, monthly, by_drink = _load_sales_detail(self.client_id, start, end)
        self._last_daily   = daily
        self._last_monthly = monthly

        total = sum(daily.values())
        self._lbl_sales_total.setText(f"합계: {total:,} 원")

        # 음료별 테이블 채우기
        rows = sorted(by_drink.items(), key=lambda x: -x[1]["total"])
        self._drink_table.setRowCount(len(rows))
        for r, (name, data) in enumerate(rows):
            self._drink_table.setItem(r, 0, QTableWidgetItem(name))
            self._drink_table.setItem(r, 1, QTableWidgetItem(str(data["count"])))
            self._drink_table.setItem(r, 2, QTableWidgetItem(f"{data['total']:,}"))

        self._draw_chart()

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
        if self.inventory.rename(drink_id, new_name):
            self._lbl_rename_result.setText(f"drink_id {drink_id} → '{new_name}' 변경 완료")
            self._refresh_inventory()
        else:
            self._lbl_rename_result.setText(f"drink_id {drink_id}를 찾을 수 없습니다.")

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
        self._spin_amount.setRange(1, 100)
        self._spin_amount.setValue(10)
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

        amount = self._spin_amount.value()
        self.inventory.restock(drink_id, amount)

        # 보충 이력 파일에 기록 (오프라인 상태에서도 동작)
        append_restock(
            date_str=datetime.date.today().isoformat(),
            client_id=self.client_id,
            drink_id=drink_id,
            drink_name=node.name,
            amount=amount,
        )
        self._lbl_restock_result.setText(
            f"'{node.name}' {amount}개 보충 완료 (현재 재고: {node.stock}개)"
        )
        self._refresh_inventory()

    # ── 탭 5: 비밀번호 변경 ───────────────────────
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
