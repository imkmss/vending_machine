#!/bin/bash
# 서버 2대 + 클라이언트 3개 한 번에 실행

# 서버 실행
python3 -m server.server_main \
    --port 9999 --sync-port 10000 \
    --peer-host localhost --peer-sync-port 10001 &

python3 -m server.server_main \
    --port 9998 --sync-port 10001 \
    --peer-host localhost --peer-sync-port 10000 &

echo "[서버] 기동 대기 중..."
sleep 2

# 클라이언트 실행
python3 main.py VM_01 &
python3 main.py VM_02 --port 9998 &
python3 main.py VM_03 &

wait
