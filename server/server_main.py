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
from server.server_handler import ClientHandler, ClientRegistry
from server.sync_manager import SyncManager
from server.web_server import start_web_server

HOST = "0.0.0.0"
PORT = 9999

logger = logging.getLogger(__name__)


class VendingServer:
    """TCP 서버 — 다중 자판기 클라이언트 연결을 수신·처리."""

    def __init__(
        self,
        host:         str           = HOST,
        port:         int           = PORT,
        data_store:   SalesDataStore  | None = None,
        sync_manager: SyncManager    | None = None,
        registry:     ClientRegistry | None = None,
    ):
        self.host         = host
        self.port         = port
        self.data_store   = data_store or SalesDataStore()
        self.sync_manager = sync_manager
        self.registry     = registry or ClientRegistry()

    def start(self, web_port: int = 8080):
        start_web_server(self.data_store, port=web_port)

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
                ClientHandler(conn, addr, self.data_store, self.sync_manager, self.registry).start()
        except KeyboardInterrupt:
            print("\n[서버] 종료")
        finally:
            server_sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="자판기 TCP 서버")
    parser.add_argument("--host",           default=HOST)
    parser.add_argument("--port",           type=int, default=PORT)
    parser.add_argument("--web-port",       type=int, default=8080,
                        help="웹 대시보드 포트 (기본 8080)")
    parser.add_argument("--sync-port",      type=int, default=None,
                        help="이 서버의 동기화 수신 포트 (e.g. 10000)")
    parser.add_argument("--peer-host",      default=None,
                        help="피어 서버 호스트 (e.g. localhost)")
    parser.add_argument("--peer-sync-port", type=int, default=None,
                        help="피어 서버의 동기화 수신 포트 (e.g. 10001)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    data_store   = SalesDataStore()
    sync_manager = None

    if args.sync_port and args.peer_host and args.peer_sync_port:
        sync_manager = SyncManager(
            my_sync_port=args.sync_port,
            peer_host=args.peer_host,
            peer_sync_port=args.peer_sync_port,
            data_store=data_store,
        )
        sync_manager.start()

    VendingServer(
        host=args.host,
        port=args.port,
        data_store=data_store,
        sync_manager=sync_manager,
    ).start(web_port=args.web_port)
