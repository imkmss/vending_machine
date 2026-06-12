"""Socket 프로그래밍으로 자판기 판매 데이터를 서버에 전송한다. 멀티 스레드로 송신·Heartbeat를 처리한다."""
from __future__ import annotations

import json
import socket
import struct
import threading
import time
import logging

from client.core.transaction import SaleRecord, SendQueue

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 프로토콜 상수
# ──────────────────────────────────────────────
PROTO_VER = 0x01

class MsgType:
    SALE      = 0x01  # Client → Server : 판매 데이터
    INVENTORY = 0x02  # Client → Server : 재고 현황
    ACK       = 0x03  # Server → Client : 수신 성공
    ERROR     = 0x04  # 양방향           : 오류
    HEARTBEAT = 0x05  # 양방향           : 연결 유지
    COMMAND   = 0x06  # Server → Client : 명령 (이름 변경 등)

HEADER_SIZE   = 12      # bytes
ACK_TIMEOUT   = 3.0     # 초 — ACK 대기 시간
MAX_RETRIES   = 3       # 재전송 횟수
RECONNECT_SEC = 5       # 재연결 대기 시간 (초)
HEARTBEAT_SEC = 30      # Heartbeat 전송 주기 (초)
HB_TIMEOUT    = 90      # Heartbeat 무응답 타임아웃 (초)

# CLIENT_ID 문자열 → 2바이트 정수
CLIENT_ID_MAP = {"VM_01": 1, "VM_02": 2, "VM_03": 3}


# ──────────────────────────────────────────────
# 헬퍼 함수
# ──────────────────────────────────────────────
def _checksum(payload: bytes) -> int:
    """단순 16비트 합산 체크섬 (Big-Endian 2 bytes)."""
    total = sum(payload) & 0xFFFF
    return total


def _build_message(msg_type: int, client_id_int: int, payload: bytes = b"") -> bytes:
    """
    고정 헤더(12 bytes) + 페이로드 직렬화.

    헤더 레이아웃 (Big-Endian):
      VER(1) | TYPE(1) | PAYLOAD_LEN(2) | TIMESTAMP(4) | CLIENT_ID(2) | CHECKSUM(2)
    """
    timestamp   = int(time.time())
    payload_len = len(payload)
    checksum    = _checksum(payload)

    header = struct.pack(
        ">BBHIHH",           # Big-Endian: B B H I H H
        PROTO_VER,           # VER         1 byte
        msg_type,            # TYPE        1 byte
        payload_len,         # PAYLOAD_LEN 2 bytes
        timestamp,           # TIMESTAMP   4 bytes
        client_id_int,       # CLIENT_ID   2 bytes
        checksum,            # CHECKSUM    2 bytes
    )
    return header + payload


def _parse_header(data: bytes) -> dict:
    """수신 메시지에서 헤더 파싱. data는 최소 HEADER_SIZE bytes 이어야 함."""
    ver, msg_type, payload_len, timestamp, client_id, checksum = struct.unpack(
        ">BBHIHH", data[:HEADER_SIZE]
    )
    return {
        "ver": ver,
        "type": msg_type,
        "payload_len": payload_len,
        "timestamp": timestamp,
        "client_id": client_id,
        "checksum": checksum,
    }


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """소켓에서 정확히 n 바이트를 읽는다. 연결 끊기면 ConnectionError."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("소켓 연결이 끊겼습니다.")
        buf += chunk
    return buf


# ──────────────────────────────────────────────
# TCP 클라이언트
# ──────────────────────────────────────────────
class VendingClient:
    """
    자판기 ↔ 서버 TCP 통신 담당.

    - sender 스레드 : SendQueue에서 SaleRecord를 꺼내 서버로 전송
    - heartbeat 스레드 : 30초마다 HEARTBEAT 전송, 90초 무응답 시 재연결
    - command 수신 : ACK 대기 루프 안에서 COMMAND(0x06) 처리
    """

    def __init__(
        self,
        client_id: str,
        server_host: str,
        server_port: int,
        send_queue: SendQueue,
        on_command=None,   # COMMAND 수신 콜백: fn(payload_dict)
    ):
        self.client_id     = client_id
        self.client_id_int = CLIENT_ID_MAP.get(client_id, 0)
        self.server_host   = server_host
        self.server_port   = server_port
        self.send_queue    = send_queue
        self.on_command    = on_command

        self._sock: socket.socket | None = None
        self._lock      = threading.Lock()      # 소켓 send 직렬화
        self._recv_lock = threading.Lock()      # 소켓 recv 직렬화
        self._connected   = False
        self._running     = False
        self._last_hb_ack = time.time()         # 마지막 ACK 수신 시각

    # ── 연결 관리 ──────────────────────────────
    def connect(self):
        """서버에 TCP 연결. 실패 시 RECONNECT_SEC 후 재시도."""
        while self._running:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(ACK_TIMEOUT)
                sock.connect((self.server_host, self.server_port))
                self._sock      = sock
                self._connected = True
                self._last_hb_ack = time.time()
                logger.info("[%s] 서버 연결 성공 %s:%d", self.client_id, self.server_host, self.server_port)
                return
            except OSError as e:
                logger.warning("[%s] 연결 실패: %s — %d초 후 재시도", self.client_id, e, RECONNECT_SEC)
                time.sleep(RECONNECT_SEC)

    def _disconnect(self):
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _reconnect(self):
        logger.warning("[%s] 재연결 시도", self.client_id)
        self._disconnect()
        time.sleep(RECONNECT_SEC)
        self.connect()

    # ── 저수준 송수신 ──────────────────────────
    def _send_raw(self, msg_type: int, payload: bytes = b"") -> bool:
        """헤더+페이로드 전송. 실패 시 False."""
        msg = _build_message(msg_type, self.client_id_int, payload)
        try:
            with self._lock:
                self._sock.sendall(msg)
            return True
        except OSError as e:
            logger.error("[%s] 전송 오류: %s", self.client_id, e)
            return False

    def _recv_message(self) -> dict | None:
        """
        헤더 → 페이로드 순으로 수신 후 파싱.
        체크섬 불일치 시 ERROR 전송 후 None 반환.
        """
        try:
            header_bytes = _recv_exact(self._sock, HEADER_SIZE)
            header = _parse_header(header_bytes)

            payload = b""
            if header["payload_len"] > 0:
                payload = _recv_exact(self._sock, header["payload_len"])

            # 체크섬 검증
            if _checksum(payload) != header["checksum"]:
                logger.error("[%s] CHECKSUM 불일치 — ERROR 전송", self.client_id)
                self._send_raw(MsgType.ERROR)
                return None

            header["payload"] = json.loads(payload) if payload else {}
            return header

        except (OSError, json.JSONDecodeError) as e:
            logger.error("[%s] 수신 오류: %s", self.client_id, e)
            return None

    # ── ACK 대기 ───────────────────────────────
    def _wait_ack(self) -> bool:
        """
        ACK(0x03) 수신 대기. COMMAND(0x06)가 먼저 오면 콜백 처리 후 계속 대기.
        ACK_TIMEOUT 초 안에 ACK 수신 못 하면 False.
        recv_lock으로 heartbeat 스레드와 sender 스레드의 동시 수신을 직렬화.
        """
        with self._recv_lock:
            deadline = time.time() + ACK_TIMEOUT
            while time.time() < deadline:
                self._sock.settimeout(max(0.1, deadline - time.time()))
                msg = self._recv_message()
                if msg is None:
                    return False
                if msg["type"] == MsgType.ACK:
                    self._last_hb_ack = time.time()
                    return True
                if msg["type"] == MsgType.COMMAND and self.on_command:
                    self.on_command(msg["payload"])
        return False

    # ── 판매 데이터 전송 ───────────────────────
    def send_sale(self, record: SaleRecord) -> bool:
        """
        SaleRecord → SALE(0x01) 메시지 전송 → ACK 대기.
        실패 시 최대 MAX_RETRIES회 재전송. 모두 실패하면 requeue.
        """
        if not self._connected:
            self.send_queue.requeue(record)
            return False

        payload = json.dumps({
            "client_id":   record.client_id,
            "date":        record.date,
            "sold_drink":  record.sold_drink,
            "daily_sales": record.daily_sales,
            "inventory":   record.inventory,
        }, ensure_ascii=False).encode("utf-8")

        for attempt in range(1, MAX_RETRIES + 1):
            if not self._send_raw(MsgType.SALE, payload):
                self._reconnect()
                continue
            if self._wait_ack():
                logger.info("[%s] SALE 전송 성공 (시도 %d)", self.client_id, attempt)
                return True
            logger.warning("[%s] ACK 미수신 — 재전송 %d/%d", self.client_id, attempt, MAX_RETRIES)

        logger.error("[%s] SALE 전송 최종 실패 — requeue", self.client_id)
        self.send_queue.requeue(record)
        return False

    # ── Heartbeat 전송 ─────────────────────────
    def send_heartbeat(self):
        self._send_raw(MsgType.HEARTBEAT)

    # ── 백그라운드 스레드 ──────────────────────
    def _sender_loop(self):
        """SendQueue를 순서대로 꺼내 서버로 전송하는 스레드."""
        while self._running:
            if self._connected and not self.send_queue.is_empty():
                record = self.send_queue.dequeue()
                if record:
                    self.send_sale(record)
            else:
                time.sleep(0.1)

    def _heartbeat_loop(self):
        """30초마다 HEARTBEAT 전송 후 ACK 수신. 90초 무응답 시 재연결."""
        while self._running:
            time.sleep(HEARTBEAT_SEC)
            if not self._connected:
                continue
            self.send_heartbeat()
            self._wait_ack()   # ACK 수신 → _last_hb_ack 갱신
            if time.time() - self._last_hb_ack > HB_TIMEOUT:
                logger.warning("[%s] Heartbeat 타임아웃 — 재연결", self.client_id)
                self._reconnect()

    # ── 시작 / 종료 ────────────────────────────
    def start(self):
        """연결 후 sender / heartbeat 스레드를 데몬으로 시작."""
        self._running = True
        self.connect()

        threading.Thread(target=self._sender_loop,    daemon=True, name="sender").start()
        threading.Thread(target=self._heartbeat_loop, daemon=True, name="heartbeat").start()
        logger.info("[%s] VendingClient 시작", self.client_id)

    def stop(self):
        self._running = False
        self._disconnect()
        logger.info("[%s] VendingClient 종료", self.client_id)
