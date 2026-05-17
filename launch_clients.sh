#!/bin/bash
# 클라이언트 3개 실행 (서버는 별도로 먼저 켜야 함)

python3 main.py VM_01 &
python3 main.py VM_02 --port 9998 &
python3 main.py VM_03 &

wait
