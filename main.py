"""자판기 클라이언트 진입점. python main.py [VM_01|VM_02|VM_03]"""
import sys

from PyQt5.QtWidgets import QApplication

from client.ui.sales_window import SalesWindow
from client.ui.admin_window import AdminWindow


def main():
    client_id = sys.argv[1] if len(sys.argv) > 1 else "VM_01"

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    sales = SalesWindow(client_id=client_id)
    sales.show()

    admin = AdminWindow(inventory=sales.inventory, client_id=client_id)
    admin.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
