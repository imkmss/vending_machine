"""
Server1 ↔ Server2 실시간 매출 동기화 모듈.

동작 구조:
  - _listener_loop : my_sync_port 에서 피어 서버의 SYNC 메시지를 수신 → data_store 기록
  - _sender_loop   : 큐에 쌓인 항목을 피어 서버의 peer_sync_port 로 전송 → SYNC_ACK 대기

서버 2대 실행 예시:
  python -m server.server_main --port 9999 --sync-port 10000 \
         --peer-host localhost --peer-sync-port 10001

  python -m server.server_main --port 9998 --sync-port 10001 \
         --peer-host localhost --peer-sync-port 10000
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from collections import deque

from client.network.client_socket import (
    HEADER_SIZE,
    _build_message,
    _checksum,
    _parse_header,
    _recv_exact,
)
from server.server_db import SalesDataStore

logger = logging.getLogger(__name__)

# 서버 간 전용 메시지 타입
SYNC     = 0x07   # Server → Server : 판매 데이터 동기화
SYNC_ACK = 0x08   # Server → Server : 동기화 수신 확인

RECONNECT_SEC = 5
ACK_TIMEOUT   = 3.0


class SyncManager:
    """Server1 ↔ Server2 실시간 매출 동기화."""

    def __init__(
        self,
        my_sync_port:   int,
        peer_host:      str,
        peer_sync_port: int,
        data_store:     SalesDataStore,
    ):
        self.my_sync_port   = my_sync_port
        self.peer_host      = peer_host
        self.peer_sync_port = peer_sync_port
        self.data_store     = data_store
        self._tag           = f"[Sync:{my_sync_port}]"   # 로그에 포트 표시

        self._queue: deque[dict] = deque()
        self._queue_lock = threading.Lock()
        self._running    = False

    # ── 시작 / 종료 ─────────────────────────────────────────────────────
    def start(self) -> None:
        self._running = True
        threading.Thread(
            target=self._listener_loop, daemon=True, name="sync-listener"
        ).start()
        threading.Thread(
            target=self._sender_loop, daemon=True, name="sync-sender"
        ).start()
        logger.info(
            "%s 시작 — 수신 :%d  피어 %s:%d",
            self._tag, self.my_sync_port, self.peer_host, self.peer_sync_port,
        )

    def stop(self) -> None:
        self._running = False

    # ── 외부 호출: 판매 데이터 동기화 큐에 추가 ─────────────────────────
    def push(self, client_id: str, date_str: str, price: int,
             drink_name: str = "", drink_price: int = 0,
             inventory: list | None = None) -> None:
        """클라이언트 SALE 처리 후 피어로 보낼 항목을 큐에 적재."""
        with self._queue_lock:
            self._queue.append({
                "client_id":   client_id,
                "date":        date_str,
                "price":       price,
                "drink_name":  drink_name,
                "drink_price": drink_price,
                "inventory":   inventory or [],
            })

    # ── 수신 루프 ───────────────────────────────────────────────────────
    def _listener_loop(self) -> None:
        """피어 서버가 보내는 SYNC 메시지를 수신해 data_store 에 기록."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self.my_sync_port))
        srv.listen(2)
        logger.info("%s 수신 대기 :%d", self._tag, self.my_sync_port)
        while self._running:
            try:
                conn, addr = srv.accept()
                logger.info("%s 피어 연결 수락: %s", self._tag, addr)
                threading.Thread(
                    target=self._handle_peer, args=(conn,), daemon=True
                ).start()
            except OSError:
                break
        srv.close()

    def _handle_peer(self, conn: socket.socket) -> None:
        """연결된 피어로부터 SYNC 메시지를 반복 수신하고 SYNC_ACK 를 반환."""
        try:
            while self._running:
                header_bytes  = _recv_exact(conn, HEADER_SIZE)
                header        = _parse_header(header_bytes)
                payload_bytes = b""
                if header["payload_len"] > 0:
                    payload_bytes = _recv_exact(conn, header["payload_len"])

                if _checksum(payload_bytes) != header["checksum"]:
                    logger.warning("%s 체크섬 불일치 — 무시", self._tag)
                    continue

                if header["type"] == SYNC:
                    data = json.loads(payload_bytes)
                    self.data_store.record_sale(
                        data["client_id"], data["date"], data["price"],
                        drink_name=data.get("drink_name", ""),
                        drink_price=data.get("drink_price", 0),
                    )
                    inventory = data.get("inventory", [])
                    if inventory:
                        self.data_store.update_inventory(data["client_id"], inventory)
                    logger.info(
                        "%s 수신 저장: %s %s %d원 (%s)",
                        self._tag, data["client_id"], data["date"], data["price"],
                        data.get("drink_name", "?"),
                    )
                    conn.sendall(_build_message(SYNC_ACK, 0))
                else:
                    logger.warning("%s 알 수 없는 타입 0x%02x", self._tag, header["type"])
        except (ConnectionError, OSError):
            logger.info("%s 피어 연결 종료", self._tag)
        finally:
            conn.close()

    # ── 송신 루프 ───────────────────────────────────────────────────────
    def _sender_loop(self) -> None:
        """큐에서 항목을 꺼내 피어 서버로 SYNC 전송, SYNC_ACK 확인."""
        sock: socket.socket | None = None

        while self._running:
            # 연결 없으면 재연결
            if sock is None:
                sock = self._connect_peer()
                if sock is None:
                    time.sleep(RECONNECT_SEC)
                    continue

            # 큐에서 항목 꺼내기 (락은 짧게)
            item = None
            with self._queue_lock:
                if self._queue:
                    item = self._queue.popleft()

            if item is None:
                time.sleep(0.05)
                continue

            # 전송 (락 밖에서 수행)
            payload = json.dumps(item, ensure_ascii=False).encode("utf-8")
            try:
                sock.sendall(_build_message(SYNC, 0, payload))
                sock.settimeout(ACK_TIMEOUT)
                hdr_bytes = _recv_exact(sock, HEADER_SIZE)
                resp      = _parse_header(hdr_bytes)
                if resp["type"] == SYNC_ACK:
                    logger.info("%s 전송 완료: %s", self._tag, item)
                else:
                    logger.warning("%s 예상 외 응답 0x%02x — 재큐", self._tag, resp["type"])
                    with self._queue_lock:
                        self._queue.appendleft(item)
            except OSError as e:
                logger.warning("%s 전송 실패: %s — 재연결", self._tag, e)
                try:
                    sock.close()
                except OSError:
                    pass
                sock = None
                with self._queue_lock:
                    self._queue.appendleft(item)

    def _connect_peer(self) -> socket.socket | None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.peer_host, self.peer_sync_port))
            logger.info("%s 피어 연결 성공 %s:%d", self._tag, self.peer_host, self.peer_sync_port)
            return s
        except OSError as e:
            logger.warning("%s 피어 연결 실패: %s", self._tag, e)
            return None
