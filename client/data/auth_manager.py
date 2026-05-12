from __future__ import annotations

import hashlib
import os
import re

_AUTH_PATH = os.path.join(os.path.dirname(__file__), "admin_auth.txt")
_DEFAULT_PW = "admin123!"


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def validate_format(pw: str) -> tuple[bool, str]:
    """형식 검증. (True, '') 또는 (False, 오류메시지) 반환."""
    if len(pw) < 8:
        return False, "8자리 이상이어야 합니다."
    if not re.search(r"\d", pw):
        return False, "숫자를 1개 이상 포함해야 합니다."
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", pw):
        return False, "특수문자를 1개 이상 포함해야 합니다."
    return True, ""


def password_exists() -> bool:
    return os.path.exists(_AUTH_PATH)


def check_password(pw: str) -> bool:
    if not password_exists():
        return False
    with open(_AUTH_PATH, "r") as f:
        return f.read().strip() == _hash(pw)


def set_password(pw: str) -> tuple[bool, str]:
    ok, msg = validate_format(pw)
    if not ok:
        return False, msg
    with open(_AUTH_PATH, "w") as f:
        f.write(_hash(pw))
    return True, "비밀번호가 설정되었습니다."


def initialize_default():
    """최초 실행 시 기본 비밀번호(admin123!)로 초기화."""
    if not password_exists():
        set_password(_DEFAULT_PW)
