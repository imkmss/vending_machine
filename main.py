"""
자판기 클라이언트 진입점.

  python main.py [VM_ID]           → 자판기 화면
  python main.py [VM_ID] --admin   → 관리자 화면
  python main.py [VM_ID] --all     → 두 창 모두
"""
import sys

from PyQt5.QtWidgets import QApplication

from client.ui.sales_window import SalesWindow
from client.ui.admin_window import AdminWindow


def main():
    args = sys.argv[1:]
    client_id = "VM_01"
    mode = "sales"

    for arg in args:
        if arg.startswith("VM_"):
            client_id = arg
        elif arg == "--admin":
            mode = "admin"
        elif arg == "--all":
            mode = "all"

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    if mode == "sales":
        sales = SalesWindow(client_id=client_id)
        sales.show()
    elif mode == "admin":
        from client.core.beverage import Inventory
        inventory = Inventory()
        admin = AdminWindow(inventory=inventory, client_id=client_id)
        admin.show()
    else:  # all
        sales = SalesWindow(client_id=client_id)
        sales.show()
        admin = AdminWindow(inventory=sales.inventory, client_id=client_id)
        admin.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
