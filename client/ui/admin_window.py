from __future__ import annotations

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFrame,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from client.core.beverage import Inventory
from client.core.sales_tree import SalesBST
from client.data.file_manager import load_sales

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib
    matplotlib.rcParams["font.family"] = "AppleGothic"   # macOS 한글 폰트
    _MPL = True
except ImportError:
    _MPL = False


def _build_bst_from_csv(client_id: str) -> SalesBST:
    """CSV 로그에서 BST를 재구성한다."""
    bst = SalesBST()
    for row in load_sales():
        if row["client_id"] == client_id:
            date_int = int(row["date"].replace("-", ""))
            bst.insert(date_int, int(row["price"]))
    return bst


def _calc_stock_from_csv(client_id: str, default_stock: int = 10) -> dict[int, int]:
    """CSV 판매 기록에서 drink_id별 현재 재고를 역산한다."""
    sold: dict[int, int] = {}
    for row in load_sales():
        if row["client_id"] == client_id:
            did = int(row["drink_id"])
            sold[did] = sold.get(did, 0) + 1
    return {did: max(0, default_stock - count) for did, count in sold.items()}


class AdminWindow(QMainWindow):
    """관리자 화면 — 재고 현황 / 매출 조회 / 음료 이름 변경."""

    def __init__(self, inventory: Inventory, client_id: str = "VM_01"):
        super().__init__()
        self.inventory = inventory
        self.client_id = client_id
        self.bst       = _build_bst_from_csv(client_id)

        self.setWindowTitle(f"관리자 — {client_id}")
        self.setFixedSize(700, 500)
        self._init_ui()

    # ── UI 구성 ───────────────────────────────
    def _init_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        tabs.addTab(self._build_inventory_tab(), "재고 현황")
        tabs.addTab(self._build_sales_tab(),     "매출 조회")
        tabs.addTab(self._build_rename_tab(),    "음료 이름 변경")

    # ── 탭 1: 재고 현황 ───────────────────────
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
        btn_refresh.setFixedHeight(36)
        btn_refresh.setStyleSheet(
            "background:#1976D2; color:white; border-radius:6px; font-size:13px;"
        )
        btn_refresh.clicked.connect(self._refresh_inventory)
        layout.addWidget(btn_refresh)

        self._refresh_inventory()
        return w

    def _refresh_inventory(self):
        nodes = self.inventory.to_list()
        self._inv_table.setRowCount(len(nodes))
        for r, node in enumerate(nodes):
            self._inv_table.setItem(r, 0, QTableWidgetItem(str(node["drink_id"])))
            self._inv_table.setItem(r, 1, QTableWidgetItem(node["name"]))
            self._inv_table.setItem(r, 2, QTableWidgetItem(f"{node['price']:,}"))
            stock_item = QTableWidgetItem(str(node["stock"]))
            stock_item.setForeground(
                Qt.red if node["stock"] < 3 else Qt.black
            )
            self._inv_table.setItem(r, 3, stock_item)

    # ── 탭 2: 매출 조회 ───────────────────────
    def _build_sales_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 날짜 범위 입력
        form = QHBoxLayout()
        form.addWidget(QLabel("시작일 (YYYYMMDD):"))
        self._edit_start = QLineEdit()
        self._edit_start.setPlaceholderText("20250401")
        form.addWidget(self._edit_start)

        form.addWidget(QLabel("종료일:"))
        self._edit_end = QLineEdit()
        self._edit_end.setPlaceholderText("20250430")
        form.addWidget(self._edit_end)

        btn_query = QPushButton("조회")
        btn_query.setFixedWidth(70)
        btn_query.setStyleSheet(
            "background:#388E3C; color:white; border-radius:6px; font-size:13px;"
        )
        btn_query.clicked.connect(self._query_sales)
        form.addWidget(btn_query)
        layout.addLayout(form)

        # 합계 라벨
        self._lbl_total = QLabel("합계: 0 원")
        self._lbl_total.setFont(QFont("맑은 고딕", 12, QFont.Bold))
        layout.addWidget(self._lbl_total)

        # 차트 또는 대체 텍스트
        if _MPL:
            self._fig    = Figure(figsize=(6, 3), tight_layout=True)
            self._canvas = FigureCanvas(self._fig)
            layout.addWidget(self._canvas)
        else:
            layout.addWidget(QLabel("matplotlib 미설치 — 차트 비활성"))

        return w

    def _query_sales(self):
        try:
            start = int(self._edit_start.text().strip())
            end   = int(self._edit_end.text().strip())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "날짜를 YYYYMMDD 형식으로 입력하세요.")
            return

        nodes  = self.bst.range_query(start, end)
        total  = sum(n.sales for n in nodes)
        self._lbl_total.setText(f"합계: {total:,} 원")

        if not _MPL or not nodes:
            return

        dates  = [str(n.date) for n in nodes]
        sales  = [n.sales for n in nodes]

        self._fig.clear()
        ax = self._fig.add_subplot(111)
        bars = ax.bar(dates, sales, color="#42A5F5")
        ax.set_xlabel("날짜")
        ax.set_ylabel("매출(원)")
        ax.set_title(f"{self.client_id} 매출 현황")
        ax.tick_params(axis="x", rotation=30)
        for bar, val in zip(bars, sales):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(sales) * 0.01,
                f"{val:,}", ha="center", va="bottom", fontsize=8,
            )
        self._canvas.draw()

    # ── 탭 3: 음료 이름 변경 ──────────────────
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

        btn_rename = QPushButton("이름 변경")
        btn_rename.setFixedHeight(40)
        btn_rename.setStyleSheet(
            "background:#F57C00; color:white; border-radius:8px; font-size:13px; font-weight:bold;"
        )
        btn_rename.clicked.connect(self._on_rename)
        layout.addWidget(btn_rename)

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
