from PyQt5.QtWidgets import QMainWindow


class SalesWindow(QMainWindow):
    """판매 화면"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("자판기 - 판매")
        self.setFixedSize(800, 600)
        self._init_ui()

    def _init_ui(self):
        pass
