"""클라이언트 연결을 멀티 스레드로 처리하고, 저재고 알림·음료 이름 변경 명령을 전송한다."""
from __future__ import annotations

import json
import logging
import socket
import threading

from client.network.client_socket import (
    MsgType, HEADER_SIZE,
    _build_message, _checksum, _parse_header, _recv_exact,
)
from server.server_db import SalesDataStore

logger = logging.getLogger(__name__)

LOW_STOCK_THRESHOLD = 3


# ── SV105: 연결 중인 클라이언트 핸들러 등록부 ──────────────────
class ClientRegistry:
    """연결 중인 자판기 핸들러 등록부: 음료 이름 변경 명령 전송에 사용한다."""

    def __init__(self):
        self._handlers: dict[str, "ClientHandler"] = {}
        self._lock = threading.Lock()

    def register(self, client_id: str, handler: "ClientHandler") -> None:
        with self._lock:
            self._handlers[client_id] = handler

    def unregister(self, client_id: str) -> None:
        with self._lock:
            self._handlers.pop(client_id, None)

    def send_rename(self, client_id: str, drink_id: int, new_name: str) -> bool:
        """연결된 자판기에 음료 이름 변경 명령 전송. 연결 없으면 False."""
        with self._lock:
            handler = self._handlers.get(client_id)
        if handler:
            handler.send_rename_cmd(drink_id, new_name)
            return True
        return False

    def connected(self) -> list[str]:
        with self._lock:
            return list(self._handlers.keys())


class ClientHandler(threading.Thread):
    """자판기 클라이언트 1대의 TCP 연결을 처리하는 멀티 스레드 핸들러."""

    def __init__(self, conn: socket.socket, addr: tuple, data_store: SalesDataStore,
                 sync_manager=None, registry: ClientRegistry | None = None):
        super().__init__(daemon=True)
        self.conn         = conn
        self.addr         = addr
        self.data_store   = data_store
        self.sync_manager = sync_manager
        self.registry     = registry
        self._client_id: str | None = None   # 첫 SALE 수신 시 확정

    def run(self):
        logger.info("[서버] 핸들러 시작 %s", self.addr)
        try:
            while True:
                header_bytes = _recv_exact(self.conn, HEADER_SIZE)
                header       = _parse_header(header_bytes)

                payload_bytes = b""
                if header["payload_len"] > 0:
                    payload_bytes = _recv_exact(self.conn, header["payload_len"])

                if _checksum(payload_bytes) != header["checksum"]:
                    logger.warning("[서버] 체크섬 불일치 from %s", self.addr)
                    self._send(MsgType.ERROR)
                    continue

                payload = json.loads(payload_bytes) if payload_bytes else {}
                self._dispatch(header["type"], payload)

        except (ConnectionError, OSError):
            logger.info("[서버] 연결 종료 %s", self.addr)
        finally:
            if self.registry and self._client_id:
                self.registry.unregister(self._client_id)
            self.conn.close()

    # ── 메시지 라우팅 ─────────────────────────────
    def _dispatch(self, msg_type: int, payload: dict):
        if msg_type == MsgType.SALE:
            self._handle_sale(payload)
        elif msg_type == MsgType.HEARTBEAT:
            self._send(MsgType.ACK)
        elif msg_type == MsgType.ERROR:
            logger.warning("[서버] ERROR 수신 from %s: %s", self.addr, payload)
        else:
            logger.warning("[서버] 알 수 없는 타입 0x%02x from %s", msg_type, self.addr)

    # ── 판매 처리 ────────────────────────────────
    def _handle_sale(self, payload: dict):
        client_id  = payload.get("client_id", str(self.addr))
        date       = payload.get("date", "")
        sold_drink = payload.get("sold_drink", {})
        price      = sold_drink.get("price", 0)
        inventory  = payload.get("inventory", [])

        drink_name = sold_drink.get("name", "")
        self.data_store.record_sale(client_id, date, price, drink_name, price)

        # SV103: 재고 현황 저장
        if inventory:
            self.data_store.update_inventory(client_id, inventory)

        # SV105: 첫 SALE 수신 시 registry에 등록
        if self.registry and self._client_id is None:
            self._client_id = client_id
            self.registry.register(client_id, self)

        logger.info(
            "[서버] SALE 저장 — %s %s %s (%d원)",
            client_id, date, drink_name or "?", price,
        )
        if self.sync_manager:
            self.sync_manager.push(
                client_id, date, price,
                drink_name=sold_drink.get("name", ""),
                drink_price=sold_drink.get("price", 0),
                inventory=inventory,
            )

        self._send(MsgType.ACK)

        # 저재고 음료 → COMMAND(low_stock) 전송
        for item in inventory:
            if item.get("stock", 99) < LOW_STOCK_THRESHOLD:
                self._send_low_stock(item)


    # ── 저재고 알림 ──────────────────────────────
    def _send_low_stock(self, item: dict):
        body = json.dumps({
            "action":   "low_stock",
            "drink_id": item["drink_id"],
            "name":     item["name"],
            "stock":    item["stock"],
        }, ensure_ascii=False).encode("utf-8")
        self._send(MsgType.COMMAND, body)
        logger.info(
            "[서버] 저재고 알림 — %s 재고 %d개", item["name"], item["stock"]
        )

    # ── SV105: 이름 변경 명령 전송 ───────────────
    def send_rename_cmd(self, drink_id: int, new_name: str) -> None:
        body = json.dumps({
            "action":   "rename",
            "drink_id": drink_id,
            "new_name": new_name,
        }, ensure_ascii=False).encode("utf-8")
        self._send(MsgType.COMMAND, body)
        logger.info("[서버] 이름 변경 명령 전송 — drink_id=%d → '%s'", drink_id, new_name)

    # ── 저수준 전송 ──────────────────────────────
    def _send(self, msg_type: int, payload: bytes = b""):
        try:
            self.conn.sendall(_build_message(msg_type, 0, payload))
        except OSError as e:
            logger.error("[서버] 전송 오류: %s", e)
