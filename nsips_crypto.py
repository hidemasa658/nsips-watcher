"""Fernet 対称鍵管理と選択フィールド暗号化。"""
from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet


def get_or_create_key(key_path: Path) -> bytes:
    """鍵ファイルが存在すればロード、なければ新規生成して保存。"""
    if key_path.exists():
        return key_path.read_bytes()
    key = Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    return key


def encrypt_field(key: bytes, plaintext: str | None) -> str | None:
    """None は None のまま。それ以外は Fernet で暗号化して URL-safe base64 文字列で返す。"""
    if plaintext is None:
        return None
    f = Fernet(key)
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_field(key: bytes, ciphertext: str | None) -> str | None:
    """None は None。それ以外は復号して UTF-8 文字列で返す。"""
    if ciphertext is None:
        return None
    f = Fernet(key)
    return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
