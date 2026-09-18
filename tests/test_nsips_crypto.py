from pathlib import Path

from nsips_crypto import decrypt_field, encrypt_field, get_or_create_key


def test_get_or_create_key_creates_new(tmp_path):
    key_path = tmp_path / ".key"
    assert not key_path.exists()
    key = get_or_create_key(key_path)
    assert isinstance(key, bytes)
    assert key_path.exists()
    assert len(key) > 0


def test_get_or_create_key_reuses_existing(tmp_path):
    key_path = tmp_path / ".key"
    k1 = get_or_create_key(key_path)
    k2 = get_or_create_key(key_path)
    assert k1 == k2


def test_encrypt_decrypt_roundtrip(tmp_path):
    key = get_or_create_key(tmp_path / ".key")
    original = "タナベ 皮フ科医院"
    enc = encrypt_field(key, original)
    assert enc != original
    assert isinstance(enc, str)
    dec = decrypt_field(key, enc)
    assert dec == original


def test_encrypt_none_returns_none(tmp_path):
    key = get_or_create_key(tmp_path / ".key")
    assert encrypt_field(key, None) is None


def test_decrypt_none_returns_none(tmp_path):
    key = get_or_create_key(tmp_path / ".key")
    assert decrypt_field(key, None) is None


def test_decrypt_wrong_key_raises(tmp_path):
    k1 = get_or_create_key(tmp_path / "k1")
    k2 = get_or_create_key(tmp_path / "k2")
    enc = encrypt_field(k1, "secret")
    import pytest
    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        decrypt_field(k2, enc)


def test_encrypt_different_each_time(tmp_path):
    key = get_or_create_key(tmp_path / ".key")
    e1 = encrypt_field(key, "same")
    e2 = encrypt_field(key, "same")
    assert e1 != e2
    assert decrypt_field(key, e1) == "same"
    assert decrypt_field(key, e2) == "same"
