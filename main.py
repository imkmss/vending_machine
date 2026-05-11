"""
자판기 클라이언트 진입점.

  python main.py [VM_ID]                        → 자판기 화면
  python main.py [VM_ID] --admin                → 관리자 화면
  python main.py [VM_ID] --all                  → 두 창 모두
  python main.py [VM_ID] --host 192.168.0.1     → 서버 주소 지정
  python main.py [VM_ID] --port 9999            → 서버 포트 지정
"""
import logging
import sys

from PyQt5.QtWidgets import QApplication

from client.ui.sales_window import SalesWindow
from client.ui.admin_window import AdminWindow


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    args = sys.argv[1:]
    client_id   = "VM_01"
    mode        = "sales"
    server_host = "127.0.0.1"
    server_port = 9999

    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("VM_"):
            client_id = arg
        elif arg == "--admin":
            mode = "admin"
        elif arg == "--all":
            mode = "all"
        elif arg == "--host" and i + 1 < len(args):
            server_host = args[i + 1]
            i += 1
        elif arg == "--port" and i + 1 < len(args):
            server_port = int(args[i + 1])
            i += 1
        i += 1

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    if mode == "sales":
        sales = SalesWindow(client_id=client_id,
                            server_host=server_host, server_port=server_port)
        sales.show()
    elif mode == "admin":
        from client.core.beverage import Inventory
        inventory = Inventory()
        admin = AdminWindow(inventory=inventory, client_id=client_id)
        admin.show()
    else:  # all
        sales = SalesWindow(client_id=client_id,
                            server_host=server_host, server_port=server_port)
        sales.show()
        admin = AdminWindow(inventory=sales.inventory, client_id=client_id)
        admin.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
