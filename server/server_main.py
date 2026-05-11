"""
자판기 TCP 서버 진입점.

  python -m server.server_main              → 기본 (0.0.0.0:9999)
  python -m server.server_main --port 8888  → 포트 지정
"""
from __future__ import annotations

import argparse
import logging
import socket

from server.server_db import SalesDataStore
from server.server_handler import ClientHandler

HOST = "0.0.0.0"
PORT = 9999

logger = logging.getLogger(__name__)


class VendingServer:
    """TCP 서버 — 다중 자판기 클라이언트 연결을 수신·처리."""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host       = host
        self.port       = port
        self.data_store = SalesDataStore()

    def start(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))
        server_sock.listen(10)
        print(f"[서버] 시작 — {self.host}:{self.port}  (Ctrl-C 종료)")
        logger.info("서버 시작 — %s:%d", self.host, self.port)

        try:
            while True:
                conn, addr = server_sock.accept()
                print(f"[서버] 클라이언트 연결: {addr}")
                logger.info("클라이언트 연결: %s", addr)
                ClientHandler(conn, addr, self.data_store).start()
        except KeyboardInterrupt:
            print("\n[서버] 종료")
        finally:
            server_sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="자판기 TCP 서버")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    VendingServer(host=args.host, port=args.port).start()
