import sys
from PyQt5.QtWidgets import QApplication
from ui.sales_window import SalesWindow


def main():
    app = QApplication(sys.argv)
    window = SalesWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
