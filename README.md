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
    { "drink_id": 1, "name": "믹스커피",    "price": 200, "stock": 10 },
    { "drink_id": 2, "name": "고급믹스커피", "price": 300, "stock": 10 },
    { "drink_id": 3, "name": "물",          "price": 450, "stock": 10 },
    { "drink_id": 4, "name": "캔커피",      "price": 500, "stock": 10 },
    { "drink_id": 5, "name": "이온음료",    "price": 550, "stock": 10 },
    { "drink_id": 6, "name": "고급캔커피",  "price": 700, "stock": 10 },
    { "drink_id": 7, "name": "탄산음료",    "price": 750, "stock": 10 },
    { "drink_id": 8, "name": "특화음료",    "price": 800, "stock": 10 }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `client_id` | 어느 자판기인지 식별 |
| `date` | 일별 매출 집계 기준일 |
| `daily_sales` | 하루 총 매출 (단위: 원) |
| `inventory` | 8종 음료의 가격·재고 배열 |
| `inventory[].drink_id` | 음료 고유 ID (1~8) |
| `inventory[].name` | 음료 이름 |
| `inventory[].price` | 음료 단가 (단위: 원) |
| `inventory[].stock` | 현재 재고 수량 |

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
┌─────────────────────────────────────────────────────┐
│  애플리케이션 계층  (Application Layer)                 │
│                                                     │
│  { "client_id": "VM_01", "daily_sales": 100000 ... }│
│  ← JSON 문자열을 UTF-8 바이트로 인코딩                    │
└─────────────────────────────────────────────────────┘
                        ↓  + TCP 헤더
┌─────────────────────────────────────────────────────┐
│  Segment  (Transport Layer)                         │
│                                                     │
│  ┌──────────────┬──────────────────────────────┐    │
│  │  TCP Header  │         Data (JSON)          │    │
│  ├──────────────┴──────────────────────────────┤    │
│  │ Src Port  : 50123  (자판기 임의 포트)           │    │
│  │ Dst Port  : 9000   (서버 수신 포트)             │    │
│  │ Seq Number: 순서 번호 (재조립용)                 │    │
│  │ ACK Number: 확인 응답 번호                     │    │
│  │ Flags     : SYN / ACK / FIN 등               │    │
│  │ Checksum  : 오류 검출용                         │    │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                        ↓  + IP 헤더
┌─────────────────────────────────────────────────────┐
│  Packet  (Internet Layer)                           │
│                                                     │
│  ┌───────────┬──────────────────────────────────┐   │
│  │ IP Header │     Segment (TCP Header + Data)  │   │
│  ├───────────┴──────────────────────────────────┤   │
│  │ Src IP  : 192.168.0.5  (자판기 IP)             │   │
│  │ Dst IP  : 192.168.0.10 (서버 IP)              │   │
│  │ Protocol: 6 (TCP 식별값)                       │   │
│  │ TTL     : 패킷 수명 (홉마다 1씩 감소)              │   │
│  │ Checksum: 오류 검출용                           │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                        ↓  + 이더넷 헤더 & 트레일러
┌─────────────────────────────────────────────────────┐
│  Frame  (Network Access Layer)                      │
│                                                     │
│  ┌──────────┬──────────────────────────┬─────────┐  │
│  │Eth Header│  Packet (IP + TCP + Data)│ Trailer │  │
│  ├──────────┴──────────────────────────┴─────────┤  │
│  │ Dst MAC : 다음 홉의 MAC 주소 (구간마다 갱신)         │  │
│  │ Src MAC : 현재 장치의 MAC 주소                    │  │
│  │ Type    : 0x0800 (IPv4 식별값)                  │  │
│  │ Trailer : FCS (Frame Check Sequence, 오류검출)│    │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                        ↓
                  비트(Bit Stream)로 변환 → 전송
```

| 계층 | PDU | 주요 헤더 정보 |
|------|-----|--------------|
| Application | Data | JSON 페이로드 (UTF-8 인코딩) |
| Transport | Segment | Src Port: 50123 → Dst Port: 9000 / Seq·ACK 번호 / Flags / Checksum |
| Internet | Packet | Src IP: 192.168.0.5 → Dst IP: 192.168.0.10 / Protocol: 6 / TTL |
| Network Access | Frame | MAC 주소 (구간마다 갱신) / Type: 0x0800 / FCS 트레일러 |

> MAC 주소는 라우터를 거칠 때마다 다음 홉 주소로 교체됩니다. IP 주소는 출발지~목적지까지 유지됩니다.

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

**Client ↔ Server: TCP 소켓**
- 판매 데이터는 유실되면 안 되므로 ACK + 재전송으로 전달을 보장하는 TCP 선택
- 3-way Handshake로 연결을 확인하고, Sequence Number로 순서를 보장

**Server ↔ Server: Raw 소켓 (사용자 정의 프로토콜)**
- TCP/UDP 어느 쪽도 아닌 새로운 프로토콜 번호를 IP 헤더의 Protocol 필드에 직접 지정해야 하므로 Raw 소켓(IP 직접 제어) 선택

### 서버 기능 접근
- 서버의 관리 메뉴는 **웹 페이지**로도 접근 가능해야 한다.

---

### Protocol Requirement

#### 1) 메시지 타입 정의

| 타입 코드 | 이름 | 방향 | 설명 |
|----------|------|------|------|
| `0x01` | SALE | Client → Server | 음료 판매 데이터 전송 |
| `0x02` | INVENTORY | Client → Server | 재고 현황 전송 |
| `0x03` | ACK | Server → Client | 수신 성공 응답 |
| `0x04` | ERROR | 양방향 | 오류 발생 알림 |
| `0x05` | HEARTBEAT | 양방향 | 연결 유지 확인 |
| `0x06` | COMMAND | Server → Client | 명령 전달 (이름 변경 등) |
| `0x07` | SYNC | Server ↔ Server | Raw 소켓 동기화 데이터 |
| `0x08` | SYNC_ACK | Server ↔ Server | 동기화 수신 확인 |

---

#### 2) TCP 메시지 구조 (Client ↔ Server)

모든 메시지는 **고정 헤더(12 bytes) + 가변 페이로드(JSON)** 로 구성됩니다.

```
 0       1       2       3       4       5       6       7  (byte)
┌───────┬───────┬───────────────┬──────────────────────────┐
│  VER  │  TYPE │  PAYLOAD_LEN  │        TIMESTAMP         │
│ 1byte │ 1byte │    2bytes     │         4bytes           │
├───────┴───────┴───────────────┼──────────────────────────┤
│          CLIENT_ID            │         CHECKSUM         │s
│           2bytes              │          2bytes          │
└───────────────────────────────┴──────────────────────────┘
│                    PAYLOAD (JSON, 가변)                   │
└───────────────────────────────────────────────────────────┘
```

| 필드 | 크기 | 설명 |
|------|------|------|
| VER | 1 byte | 프로토콜 버전 (현재 `0x01`) |
| TYPE | 1 byte | 메시지 타입 코드 |
| PAYLOAD_LEN | 2 bytes | 페이로드 길이 (bytes) |
| TIMESTAMP | 4 bytes | Unix timestamp (메시지 생성 시각) |
| CLIENT_ID | 2 bytes | 자판기 식별자 (VM_01=1, VM_02=2, VM_03=3) |
| CHECKSUM | 2 bytes | 페이로드 오류 검출값 |
| PAYLOAD | 가변 | JSON 데이터 (UTF-8 인코딩) |

---

#### 3) Raw 소켓 메시지 구조 (Server ↔ Server)

IP 헤더의 Protocol 필드에 사용자 정의 번호(`0xFD`)를 지정합니다.
그 뒤에 붙는 커스텀 헤더 구조는 다음과 같습니다.

```
 0       1       2       3       4       5       6       7  (byte)
┌───────┬───────┬───────────────┬──────────────────────────┐
│PROTO  │  TYPE │    SEQ_NUM    │        TIMESTAMP         │
│ 1byte │ 1byte │    2bytes     │         4bytes           │
├───────┴───────┴───────────────┼──────────────────────────┤
│        PAYLOAD_LEN            │         CHECKSUM         │
│           2bytes              │          2bytes          │
└───────────────────────────────┴──────────────────────────┘
│                    PAYLOAD (JSON, 가변)                   │
└───────────────────────────────────────────────────────────┘
```

| 필드 | 크기 | 설명 |
|------|------|------|
| PROTO | 1 byte | 사용자 정의 프로토콜 번호 (`0xFD`) |
| TYPE | 1 byte | `0x07` SYNC / `0x08` SYNC_ACK |
| SEQ_NUM | 2 bytes | 동기화 순서 번호 (중복 수신 방지) |
| TIMESTAMP | 4 bytes | Unix timestamp |
| PAYLOAD_LEN | 2 bytes | 페이로드 길이 |
| CHECKSUM | 2 bytes | 오류 검출값 |
| PAYLOAD | 가변 | 동기화할 판매·재고 JSON |

---

#### 4) 오류 처리 규칙

| 상황 | 처리 방법 |
|------|---------|
| ACK 미수신 (3초 초과) | 최대 3회 재전송, 이후 Queue에 보관 후 재연결 시 전송 |
| CHECKSUM 불일치 | ERROR 메시지 응답, 송신 측 재전송 요청 |
| 연결 끊김 | 5초 간격으로 재연결 시도, SendQueue 데이터 유지 |
| SYNC_ACK 미수신 | 3회 재전송 후 실패 로그 기록 |

---

#### 5) Heartbeat (연결 유지)

```
Client ──── HEARTBEAT (0x05) ────▶ Server
Client ◀─── ACK       (0x03) ──── Server

주기 : 30초마다 전송
타임아웃 : 90초 동안 응답 없으면 연결 끊김으로 판단 → 재연결 시도
```

---

#### 6) 메시지 처리 규칙 요약

- 모든 메시지는 **Big-Endian** 바이트 순서를 따른다
- PAYLOAD_LEN이 0이면 페이로드 없음 (HEARTBEAT, ACK 등)
- SEQ_NUM은 서버 재시작 시 0으로 초기화
- 동일 SEQ_NUM의 SYNC 메시지를 중복 수신하면 무시하고 SYNC_ACK만 재전송

---

## 5. 자료구조 설계

### 전체 배치 요약

| 자료구조 | 적용 위치 | 역할 |
|---------|----------|------|
| Linked List | 음료 재고 목록 | 8종 음료 노드를 연결하여 재고 관리 |
| Stack | 거스름돈 계산 | 동전 단위를 push, 반환 시 pop |
| Queue | 서버 전송 대기열 | 판매 데이터를 순서대로 서버에 전송 |
| BST (Tree) | 매출 로그 | 날짜 기준 이진 탐색 트리로 저장·조회 |
| Sort | 음료 목록 | 가격순(선택 정렬), 판매량순(퀵 정렬) |
| Search | 음료·매출 검색 | 선형 탐색(재고), 이진 탐색(매출 로그) |

---

### ① Linked List — 음료 재고 목록

8종 음료 각각을 노드로 만들어 연결합니다.
재고 추가·삭제 시 노드를 동적으로 삽입·제거합니다.

```
[믹스커피|200|10] → [고급믹스커피|300|10] → [물|450|10] → ... → [특화음료|800|10] → None
```

```python
class DrinkNode:
    def __init__(self, drink_id, name, price, stock):
        self.drink_id = drink_id
        self.name     = name
        self.price    = price
        self.stock    = stock
        self.next     = None   # 다음 노드 포인터

class Inventory:
    def __init__(self):
        self.head = None       # 첫 번째 음료 노드
```

---

### ② Stack — 거스름돈 계산

거스름돈을 계산할 때 동전 단위(500→100→50→10)를 순서대로 push합니다.
반환 시 pop하여 출력하면 큰 단위부터 자동으로 처리됩니다.

```
잔액 670원 계산 과정:

push(500, 1개)   →  [ (500, 1) ]
push(100, 1개)   →  [ (500, 1) | (100, 1) ]
push(50,  1개)   →  [ (500, 1) | (100, 1) | (50, 1) ]
push(10,  2개)   →  [ (500, 1) | (100, 1) | (50, 1) | (10, 2) ]

pop 순서대로 출력 → 10원 2개, 50원 1개, 100원 1개, 500원 1개 반환
```

```python
class ChangeStack:
    def __init__(self):
        self.stack = []

    def push(self, unit, count):
        self.stack.append((unit, count))

    def pop(self):
        return self.stack.pop() if self.stack else None
```

---

### ③ Queue — 서버 전송 대기열

판매가 발생하면 즉시 서버에 전송하지 않고 큐에 enqueue합니다.
별도 전송 스레드가 순서대로 dequeue하여 TCP 소켓으로 서버에 전달합니다.
네트워크 지연·오류 상황에서도 판매 데이터 유실을 방지합니다.

```
판매 발생  →  enqueue(판매데이터)  →  [ VM_01 | VM_02 | VM_01 ]
                                              ↓ dequeue
                                        TCP 전송 → Server
```

```python
from collections import deque

class SendQueue:
    def __init__(self):
        self.queue = deque()

    def enqueue(self, data):
        self.queue.append(data)

    def dequeue(self):
        return self.queue.popleft() if self.queue else None
```

---

### ④ BST (Tree) — 매출 로그

서버에서 날짜를 키로 매출 데이터를 BST에 저장합니다.
날짜(YYYYMMDD 정수)를 기준으로 좌(작은 날짜) / 우(큰 날짜) 배치합니다.
특정 날짜 또는 날짜 범위 조회 시 O(log n) 탐색이 가능합니다.

```
            [20250415]
           /          \
     [20250414]     [20250416]
     /                       \
[20250413]               [20250417]
```

```python
class SalesNode:
    def __init__(self, date, sales):
        self.date  = date   # 정수 YYYYMMDD
        self.sales = sales  # 해당 날짜 매출 데이터
        self.left  = None
        self.right = None

class SalesBST:
    def __init__(self):
        self.root = None

    def insert(self, date, sales): ...
    def search(self, date): ...        # 이진 탐색
    def inorder(self): ...             # 날짜 오름차순 출력
```

---

### ⑤ Sort — 음료 목록 정렬

| 정렬 | 기준 | 사용 시점 |
|------|------|---------|
| 선택 정렬 (Selection Sort) | 가격 오름차순 | 구매 가능 음료 표시 시 |
| 퀵 정렬 (Quick Sort) | 판매량 내림차순 | 관리자 화면 — 인기 음료 순위 |

```
선택 정렬 (가격순):
[700, 200, 450, 300, 500, 550, 750, 800]
→ [200, 300, 450, 500, 550, 700, 750, 800]

퀵 정렬 (판매량순):
pivot 기준으로 좌/우 분할 반복 → 인기 음료 상위 노출
```

---

### ⑥ Search — 음료·매출 검색

| 탐색 | 대상 | 방식 |
|------|------|------|
| 선형 탐색 (Linear Search) | 재고 Linked List | head부터 순차 탐색으로 음료 찾기 |
| 이진 탐색 (Binary Search) | BST 매출 로그 | 날짜 기준 좌/우 분기로 O(log n) 탐색 |

```
선형 탐색 — drink_id로 재고 노드 탐색:
head → [1] → [2] → [3] → ... → 일치 시 반환

이진 탐색 — 날짜로 매출 로그 탐색:
root(20250415) → 크면 오른쪽, 작으면 왼쪽 → 일치 시 반환
```

---

## 6. 화폐 입력 모듈 설계

### 사용 언어 및 라이브러리

| 목적 | 라이브러리 |
|------|-----------|
| TCP/Raw 소켓 통신 | `socket` (표준) |
| 동적 메모리 할당 (`malloc`/`free`) | `ctypes` (표준) |
| JSON 직렬화 | `json` (표준) |

---

### 요구사항 정리

| 항목 | 내용 |
|------|------|
| 허용 단위 | 10원, 50원, 100원, 500원, 1,000원 |
| 지폐(1,000원) 상한 | 5,000원 이하 |
| 총 투입 상한 | 7,000원 이하 |
| 투입 변수 | 반드시 **동적 할당** (`ctypes.malloc`) |
| 메모리 해제 시점 | 음료 판매 완료 또는 화폐 반환 시 `ctypes.free()` |
| UI 연동 | 투입 금액 갱신 시 구매 가능 음료 목록 실시간 갱신 |

---

### 데이터 구조

```python
import ctypes

# C 구조체와 동일한 메모리 레이아웃 정의
class CoinSlot(ctypes.Structure):
    _fields_ = [
        ("slot",       ctypes.c_int * 5),  # [10, 50, 100, 500, 1000] 단위별 개수
        ("total",      ctypes.c_int),       # 현재 총 투입 금액 (원)
        ("bill_total", ctypes.c_int),       # 지폐(1,000원)만 합산한 금액
    ]

coin = None  # 동적 할당 전까지 None 유지
```

> `slot` 인덱스 매핑: 0→10원, 1→50원, 2→100원, 3→500원, 4→1,000원

---

### 상태 흐름

```
[대기 화면]
     │
     │ 첫 화폐 투입
     ▼
coin = init_coin()   ← ctypes로 동적 할당 & 0 초기화
     │
     ▼
[insert_coin(amount) 호출]
  ├─ ① 단위 유효성 검사
  │     → 10/50/100/500/1000 이외 → 반려 (INVALID_UNIT)
  │
  ├─ ② 지폐 상한 검사  (amount == 1000)
  │     → bill_total + 1000 > 5000 → 반려 (BILL_LIMIT)
  │
  ├─ ③ 총액 상한 검사
  │     → total + amount > 7000 → 반려 (TOTAL_LIMIT)
  │
  └─ ④ 통과 → slot[i]++, total 갱신, bill_total 갱신
              → get_available_drinks() 호출하여 UI 갱신
     │
     ├──[음료 선택]
     │   ① 재고 확인
     │   ② total >= price 확인
     │   ③ 재고 차감
     │   ④ 거스름돈 = total - price → calc_change()
     │   ⑤ 판매 데이터 JSON 구조화 → TCP로 서버 전송
     │   ⑥ release_coin()  ← free() 후 None 대입
     │
     └──[반환 버튼]
         ① calc_change(total) 로 단위별 반환 개수 출력
         ② release_coin()  ← free() 후 None 대입
```

---

### 핵심 함수 목록

| 함수 | 역할 |
|------|------|
| `init_coin()` | `ctypes`로 CoinSlot 동적 할당 및 0 초기화, 포인터 반환 |
| `insert_coin(coin, amount)` | 유효성 3단계 검사 후 슬롯 반영, 오류 코드 반환 |
| `get_available_drinks(coin, drinks)` | total 기준 구매 가능 음료 목록 반환 |
| `calc_change(remain)` | 큰 단위부터 그리디로 거스름돈 계산 |
| `release_coin(coin)` | `ctypes.free()` 호출 후 `None` 반환 |

```python
VALID_UNITS  = [10, 50, 100, 500, 1000]
UNIT_INDEX   = {10: 0, 50: 1, 100: 2, 500: 3, 1000: 4}
CHANGE_UNITS = [500, 100, 50, 10]

# 오류 코드
OK            = 0
INVALID_UNIT  = 1
BILL_LIMIT    = 2
TOTAL_LIMIT   = 3
```

---

### 거스름돈 계산 (그리디)

```
잔액을 큰 단위부터 순서대로 나눔

단위 순서: [500, 100, 50, 10]

예) 잔액 = 670원
  670 / 500 = 1개  → 잔액 170
  170 / 100 = 1개  → 잔액 70
   70 /  50 = 1개  → 잔액 20
   20 /  10 = 2개  → 잔액 0
```

---

### 구매 가능 음료 표시 규칙

투입 금액이 갱신될 때마다 8종 음료 순회:
- `drink["price"] <= total` AND `drink["stock"] > 0` → 활성화
- 그 외 → 비활성화 (선택 불가)

| 투입 금액 | 구매 가능 음료 |
|-----------|--------------|
| 0 ~ 199원 | 없음           |
| 200 ~ 299원 | 믹스커피(200) |
| 300 ~ 449원 | + 고급믹스커피(300) |
| 450 ~ 499원 | + 물(450)   |
| 500 ~ 549원 | + 캔커피(500) |
| 550 ~ 699원 | + 이온음료(550) |
| 700 ~ 749원 | + 고급캔커피(700) |
| 750 ~ 799원 | + 탄산음료(750) |
| 800원 이상 | 전체 8종 |

---

### 화폐 입력 시 통신 흐름

화폐 투입·반환은 **클라이언트 내부(로컬 메모리)에서만** 처리됩니다.
서버 통신은 **음료 판매 확정 시 1회만** 발생합니다.

```
[화폐 투입 / 반환]
  → 네트워크 통신 없음
  → CoinSlot 메모리(동적 할당)에서만 처리
      │
      │ 음료 선택 확정
      ▼
[판매 데이터 JSON 구조화]  ← 클라이언트
  {
    "client_id": "VM_01",
    "date": "2025-04-15",
    "sold_drink": { "drink_id": 3, "name": "물", "price": 450 },
    "daily_sales": 누적매출,
    "inventory": [ 8종 현재 재고 ]
  }
      │
      │ TCP 소켓 (3-way Handshake → 캡슐화 → 전송)
      ▼
[Server 수신 및 처리]
  ① JSON 파싱
  ② DB 매출 누적 저장
  ③ DB 재고 업데이트
  ④ 재고 부족 시 관리자 알림
  ⑤ Raw 소켓으로 상대 서버에 즉시 동기화
      │
      ▼
[Server1 ↔ Server2 동기화 완료]
      │
      ▼
[클라이언트: release_coin() → free() → coin = None]
```

> **핵심**: 화폐 투입·반환 단계에서는 네트워크를 전혀 사용하지 않습니다.
> 판매 확정 시 TCP 통신 1회로 서버 부하를 최소화합니다.

---

## 6. 전체 통신 흐름 요약

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
