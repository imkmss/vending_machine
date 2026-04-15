# 자판기 관리 프로그램

## 프로젝트 구조

```
vending_machine/
├── README.md
├── server/
└── client/
```

---

## 1. 전체 네트워크 구성

본 프로젝트는 **3개의 클라이언트(자판기)**와 **2개의 관리 서버**로 구성됩니다.

```
Client 1 (자판기 1) ─┐
Client 2 (자판기 2) ──┼──TCP Socket──▶ Server1 or Server2
Client 3 (자판기 3) ─┘                      │
                                      양방향 실시간 동기화
                                      Server1 ◀──▶ Server2
```

| 구분 | 노드 | 역할 |
|------|------|------|
| 클라이언트 | Client1, Client2, Client3 | 자판기 — 판매·재고·매출 데이터 생성 및 전송 |
| 서버 | Server1, Server2 | 데이터 수신, 관리, 실시간 동기화 |

---

## 2. 통신 과정 (단계별)

### ① 데이터 구조화

자판기 앱은 전송 전에 판매 내역과 재고 정보를 하나의 JSON 객체로 묶습니다.

```json
{
  "client_id": "VM_01",
  "date": "2025-04-15",
  "daily_sales": 100000,
  "inventory": [
    { "drink_id": 1, "name": "음료1", "stock": 3 },
    { "drink_id": 2, "name": "음료2", "stock": 2 }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `client_id` | 어느 자판기인지 식별 |
| `date` | 일별 매출 집계 기준일 |
| `daily_sales` | 하루 총 매출 (단위: 원) |
| `inventory` | 각 음료의 현재 재고 수량 배열 |

### ② TCP 소켓 연결 (3-way Handshake)

자판기가 서버에 연결을 맺는 과정입니다. 이 과정이 완료되어야 데이터를 전송할 수 있습니다.

```
Client (자판기)          Server
     │──── SYN ────────────▶│  연결 요청
     │◀─── SYN-ACK ─────────│  수락
     │──── ACK ────────────▶│  확인 — 연결 완료
```

```python
sock = socket(AF_INET, SOCK_STREAM, 0)
connect(sock, ("192.168.0.10", 9000))  # Server1 IP, 포트 9000
```

### ③ TCP 소켓 전송 — 캡슐화(Encapsulation)

JSON 데이터가 `send()` 로 전송되면, OS가 자동으로 각 계층 헤더를 붙여 프레임으로 만들어 네트워크에 내보냅니다.

```
[애플리케이션]  {"client_id":"VM_01", "daily_sales":100000, ...}
      ↓  + TCP 헤더 (포트번호, 순서번호, ACK)          → Segment
      ↓  + IP 헤더 (출발지 IP → 목적지 IP)             → Packet
      ↓  + 이더넷 헤더 (MAC 주소) + 트레일러            → Frame
      ↓
   비트(Bit Stream)로 변환 → 네트워크 전송
```

| 계층 | PDU | 주요 헤더 정보 |
|------|-----|--------------|
| Transport | Segment | Src Port: 50123 → Dst Port: 9000 / Seq 번호 |
| Internet | Packet | Src IP: 192.168.0.5 → Dst IP: 192.168.0.10 |
| Network Access | Frame | MAC 주소 (구간마다 갱신), 트레일러 |

```python
message = json.dumps(data).encode("utf-8")
send(sock, message)
```

### ④ Server → 수신 및 처리 (역캡슐화, De-encapsulation)

서버는 수신한 프레임을 역순으로 헤더를 벗겨내고, JSON을 파싱하여 DB에 저장합니다.

```
Frame 수신
  → 이더넷 헤더 제거
  → IP 헤더 제거
  → TCP 헤더 제거
  → JSON 바이트 추출
  → 파싱 & 처리
```

```python
data = json.loads(recv_bytes)

client = data["client_id"]   # "VM_01"
sales  = data["daily_sales"]  # 100000
inv    = data["inventory"]    # [{"drink_id":1,"stock":3}, ...]

DB.save_sales(client, date, sales)       # 매출 누적 저장
DB.update_inventory(client, inv)         # 재고 현황 업데이트
if inv.stock < 3:
    alert_admin(client, inv)             # 재고 부족 알림
```

처리 완료 후 TCP ACK를 자판기에 응답하고, 이어서 Server1 ↔ Server2 실시간 동기화가 수행됩니다.

### ⑤ Server1 ↔ Server2 : 실시간 동기화

한 서버가 클라이언트로부터 데이터를 수신하면, 즉시 상대 서버에도 동일한 데이터를 동기화합니다.

- 임의의 Client에서 임의의 Server로만 데이터를 보내도, 두 Server가 가진 데이터는 항상 동일해야 합니다.
- 동기화 방식: **Raw 소켓**을 사용하여 새로운 프로토콜 타입을 정의한 패킷으로 처리합니다.

```
Server1  ◀──── Raw Socket (사용자 정의 프로토콜) ────▶  Server2
         (실시간 양방향 동기화)
```

### ⑥ Server → Client : 명령 전달

서버는 수신 역할만 하지 않고, 자판기 쪽으로 명령을 내릴 수도 있습니다.

- 음료 재고 부족 시 → 관리자에게 알림 메시지 전송
- 음료 이름 변경 명령 → 해당 자판기로 전달
- 기타 관리 명령

---

## 3. 서버가 수행하는 기능

| 번호 | 기능 |
|------|------|
| ① | 각 자판기의 음료별 일별/월별 매출현황 합산 및 누적합산 |
| ② | 각 자판기의 일별/월별 전체 매출현황 합산 및 누적합산 |
| ③ | 각 자판기의 실시간 재고현황 파악 |
| ④ | 음료 재고 부족 시 관리자에게 알림 메시지 전송 |
| ⑤ | 각 자판기의 음료 이름 변경 명령 전달 |
| ⑥ | Server1 ↔ Server2 실시간 데이터 동기화 |

---

## 4. 핵심 요구사항

### 동기화 조건
- 임의의 Client → 임의의 Server로 데이터를 전송해도 **두 서버의 데이터는 항상 동일**해야 한다.
- 동기화는 **실시간**으로 이루어져야 한다.

### 프로토콜
- Client ↔ Server 통신: **TCP 소켓**
- Server ↔ Server 동기화: **Raw 소켓** (새로운 프로토콜 타입을 직접 정의)

### 서버 기능 접근
- 서버의 관리 메뉴는 **웹 페이지**로도 접근 가능해야 한다.

---

## 5. 전체 통신 흐름 요약

```
┌──────────────────────────────────────────────────────────┐
│                     자판기 (Clients)                       │
│                                                          │
│  [Client1]        [Client2]        [Client3]             │
│  JSON 구조화       JSON 구조화       JSON 구조화            │
│  3-way Handshake  3-way Handshake  3-way Handshake       │
└──────┬──────────────────┬──────────────────┬─────────────┘
       │                  │                  │
       │    TCP Socket 전송 (캡슐화: Data → Segment → Packet → Frame)
       ▼                  ▼                  ▼
┌──────────────────────────────────────────────────────────┐
│                    관리 서버 (Servers)                      │
│                                                          │
│  ┌──────────────────┐   Raw Socket    ┌────────────────┐  │
│  │    Server 1      │◀─────────────▶│   Server 2     │  │
│  │  수신·파싱·DB저장  │  (사용자 정의)   │ 수신·파싱·DB저장 │  │
│  │  재고 알림 전송   │  실시간 동기화   │  재고 알림 전송  │  │
│  └──────────────────┘                └────────────────┘  │
└──────────────────────────────────────────────────────────┘
```
