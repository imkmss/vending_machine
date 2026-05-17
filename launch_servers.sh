#!/bin/bash
# 서버 2대 실행 (Server1: 9999, Server2: 9998)

python3 -m server.server_main \
    --port 9999 --sync-port 10000 \
    --peer-host localhost --peer-sync-port 10001 &

python3 -m server.server_main \
    --port 9998 --sync-port 10001 \
    --peer-host localhost --peer-sync-port 10000 &

echo "[서버] Server1(9999), Server2(9998) 실행 중..."
wait
