import pytest

from app.core.security import PasswordTooLongError, hash_password, verify_password


def test_hash_is_not_the_password_and_verifies():
    hashed = hash_password("Correct-Horse-7")

    assert hashed != "Correct-Horse-7"
    assert hashed.startswith("$2b$")  # bcrypt format
    assert verify_password("Correct-Horse-7", hashed)


def test_wrong_password_is_rejected():
    hashed = hash_password("Correct-Horse-7")

    assert not verify_password("correct-horse-7", hashed)
    assert not verify_password("", hashed)


def test_same_password_gives_different_hashes():
    # a random salt per hash: equal passwords cannot be spotted in the database
    assert hash_password("same-password") != hash_password("same-password")


def test_password_of_exactly_72_bytes_is_accepted():
    password = "a" * 72
    assert verify_password(password, hash_password(password))


def test_password_over_72_bytes_is_rejected():
    with pytest.raises(PasswordTooLongError):
        hash_password("a" * 73)


def test_limit_counts_bytes_not_characters():
    password = "é" * 37  # 37 characters but 74 bytes in UTF-8
    with pytest.raises(PasswordTooLongError):
        hash_password(password)


def test_verifying_an_overlong_password_returns_false():
    hashed = hash_password("a" * 72)
    # same first 72 bytes: bcrypt alone would accept it, the helper must not
    assert not verify_password("a" * 72 + "extra", hashed)
