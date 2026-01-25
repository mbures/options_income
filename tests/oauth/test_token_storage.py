"""Tests for OAuth token storage module."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.oauth.exceptions import TokenStorageError
from src.oauth.token_storage import TokenData, TokenStorage


class TestTokenData:
    """Tests for TokenData class."""

    def test_token_data_creation(self):
        """TokenData can be created with all required fields."""
        now = datetime.now(timezone.utc).isoformat()
        token = TokenData(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            token_type="Bearer",
            expires_in=1800,
            scope="read write",
            issued_at=now,
        )

        assert token.access_token == "access_token_123"
        assert token.refresh_token == "refresh_token_456"
        assert token.token_type == "Bearer"
        assert token.expires_in == 1800
        assert token.scope == "read write"
        assert token.issued_at == now

    def test_expires_at_property(self):
        """expires_at calculates correct expiration datetime."""
        issued = datetime(2026, 1, 25, 10, 0, 0, tzinfo=timezone.utc)
        token = TokenData(
            access_token="token",
            refresh_token="refresh",
            token_type="Bearer",
            expires_in=1800,  # 30 minutes
            scope="",
            issued_at=issued.isoformat(),
        )

        expected = issued + timedelta(seconds=1800)
        assert token.expires_at == expected

    def test_expires_at_with_naive_datetime(self):
        """expires_at handles naive datetime (adds UTC timezone)."""
        # Naive datetime (no timezone info)
        issued = datetime(2026, 1, 25, 10, 0, 0)
        token = TokenData(
            access_token="token",
            refresh_token="refresh",
            token_type="Bearer",
            expires_in=1800,
            scope="",
            issued_at=issued.isoformat(),
        )

        # Should add UTC timezone and calculate expiry
        expected = datetime(2026, 1, 25, 10, 30, 0, tzinfo=timezone.utc)
        assert token.expires_at == expected

    def test_is_expired_when_not_expired(self):
        """is_expired returns False for valid token."""
        # Token issued 10 minutes ago, expires in 20 minutes
        issued = datetime.now(timezone.utc) - timedelta(minutes=10)
        token = TokenData(
            access_token="token",
            refresh_token="refresh",
            token_type="Bearer",
            expires_in=1800,  # 30 minutes
            scope="",
            issued_at=issued.isoformat(),
        )

        assert token.is_expired is False

    def test_is_expired_when_expired(self):
        """is_expired returns True for expired token."""
        # Token issued 40 minutes ago, expired 10 minutes ago
        issued = datetime.now(timezone.utc) - timedelta(minutes=40)
        token = TokenData(
            access_token="token",
            refresh_token="refresh",
            token_type="Bearer",
            expires_in=1800,  # 30 minutes
            scope="",
            issued_at=issued.isoformat(),
        )

        assert token.is_expired is True

    def test_expires_within_true(self):
        """expires_within returns True when token expires soon."""
        # Token issued 25 minutes ago, expires in 5 minutes
        issued = datetime.now(timezone.utc) - timedelta(minutes=25)
        token = TokenData(
            access_token="token",
            refresh_token="refresh",
            token_type="Bearer",
            expires_in=1800,  # 30 minutes total
            scope="",
            issued_at=issued.isoformat(),
        )

        # Check if expires within 10 minutes (it expires in 5)
        assert token.expires_within(600) is True

    def test_expires_within_false(self):
        """expires_within returns False when token has time left."""
        # Token issued 10 minutes ago, expires in 20 minutes
        issued = datetime.now(timezone.utc) - timedelta(minutes=10)
        token = TokenData(
            access_token="token",
            refresh_token="refresh",
            token_type="Bearer",
            expires_in=1800,  # 30 minutes
            scope="",
            issued_at=issued.isoformat(),
        )

        # Check if expires within 5 minutes (it expires in 20)
        assert token.expires_within(300) is False

    def test_to_dict(self):
        """to_dict converts TokenData to dictionary."""
        now = datetime.now(timezone.utc).isoformat()
        token = TokenData(
            access_token="access",
            refresh_token="refresh",
            token_type="Bearer",
            expires_in=1800,
            scope="read",
            issued_at=now,
        )

        data = token.to_dict()

        assert isinstance(data, dict)
        assert data["access_token"] == "access"
        assert data["refresh_token"] == "refresh"
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 1800
        assert data["scope"] == "read"
        assert data["issued_at"] == now

    def test_from_dict(self):
        """from_dict creates TokenData from dictionary."""
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "access_token": "access",
            "refresh_token": "refresh",
            "token_type": "Bearer",
            "expires_in": 1800,
            "scope": "read",
            "issued_at": now,
        }

        token = TokenData.from_dict(data)

        assert token.access_token == "access"
        assert token.refresh_token == "refresh"
        assert token.token_type == "Bearer"
        assert token.expires_in == 1800
        assert token.scope == "read"
        assert token.issued_at == now

    def test_roundtrip_to_dict_from_dict(self):
        """TokenData can be serialized and deserialized."""
        original = TokenData(
            access_token="access",
            refresh_token="refresh",
            token_type="Bearer",
            expires_in=1800,
            scope="read write",
            issued_at=datetime.now(timezone.utc).isoformat(),
        )

        data = original.to_dict()
        restored = TokenData.from_dict(data)

        assert restored.access_token == original.access_token
        assert restored.refresh_token == original.refresh_token
        assert restored.token_type == original.token_type
        assert restored.expires_in == original.expires_in
        assert restored.scope == original.scope
        assert restored.issued_at == original.issued_at


class TestTokenStorage:
    """Tests for TokenStorage class."""

    @pytest.fixture
    def temp_token_file(self):
        """Create temporary token file path."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name
        yield path
        # Cleanup
        Path(path).unlink(missing_ok=True)

    @pytest.fixture
    def sample_token_data(self):
        """Create sample token data for testing."""
        return TokenData(
            access_token="access_abc123",
            refresh_token="refresh_xyz789",
            token_type="Bearer",
            expires_in=1800,
            scope="trading market_data",
            issued_at=datetime.now(timezone.utc).isoformat(),
        )

    def test_storage_initialization(self, temp_token_file):
        """TokenStorage can be initialized."""
        storage = TokenStorage(temp_token_file)
        assert storage.token_file == Path(temp_token_file)

    def test_storage_creates_parent_directory(self):
        """TokenStorage creates parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = f"{tmpdir}/subdir/tokens.json"
            storage = TokenStorage(token_file)

            assert Path(tmpdir, "subdir").exists()
            assert Path(tmpdir, "subdir").is_dir()

    def test_save_writes_token_file(self, temp_token_file, sample_token_data):
        """save() writes tokens to file."""
        storage = TokenStorage(temp_token_file)
        storage.save(sample_token_data)

        assert Path(temp_token_file).exists()

        # Verify content
        with open(temp_token_file, "r") as f:
            data = json.load(f)

        assert data["access_token"] == "access_abc123"
        assert data["refresh_token"] == "refresh_xyz789"

    def test_save_sets_secure_permissions(self, temp_token_file, sample_token_data):
        """save() sets file permissions to 600."""
        storage = TokenStorage(temp_token_file)
        storage.save(sample_token_data)

        file_path = Path(temp_token_file)
        stat = file_path.stat()
        # Check permissions (600 = 0o600)
        # Note: On some systems this might not work perfectly, so we just check it's restricted
        assert (stat.st_mode & 0o777) == 0o600

    def test_save_raises_on_io_error(self):
        """save() raises TokenStorageError on I/O errors."""
        # Use a path that exists but is a directory (can't write to it as a file)
        with tempfile.TemporaryDirectory() as tmpdir:
            # Try to use the directory itself as the file path
            storage = TokenStorage(tmpdir)

            token_data = TokenData(
                access_token="access",
                refresh_token="refresh",
                token_type="Bearer",
                expires_in=1800,
                scope="",
                issued_at=datetime.now(timezone.utc).isoformat(),
            )

            with pytest.raises(TokenStorageError, match="Failed to save tokens"):
                storage.save(token_data)

    def test_load_returns_token_data(self, temp_token_file, sample_token_data):
        """load() returns TokenData from file."""
        storage = TokenStorage(temp_token_file)
        storage.save(sample_token_data)

        loaded = storage.load()

        assert loaded is not None
        assert loaded.access_token == sample_token_data.access_token
        assert loaded.refresh_token == sample_token_data.refresh_token
        assert loaded.token_type == sample_token_data.token_type

    def test_load_returns_none_when_file_missing(self, temp_token_file):
        """load() returns None when file doesn't exist."""
        storage = TokenStorage(temp_token_file)
        loaded = storage.load()
        assert loaded is None

    def test_load_returns_none_on_corrupted_json(self, temp_token_file):
        """load() returns None for corrupted JSON file."""
        storage = TokenStorage(temp_token_file)

        # Write invalid JSON
        with open(temp_token_file, "w") as f:
            f.write("{ this is not valid json }")

        loaded = storage.load()
        assert loaded is None

    def test_load_returns_none_on_missing_fields(self, temp_token_file):
        """load() returns None when required fields are missing."""
        storage = TokenStorage(temp_token_file)

        # Write JSON with missing fields
        with open(temp_token_file, "w") as f:
            json.dump({"access_token": "token"}, f)  # Missing other required fields

        loaded = storage.load()
        assert loaded is None

    def test_delete_removes_file(self, temp_token_file, sample_token_data):
        """delete() removes token file."""
        storage = TokenStorage(temp_token_file)
        storage.save(sample_token_data)

        assert Path(temp_token_file).exists()

        result = storage.delete()

        assert result is True
        assert not Path(temp_token_file).exists()

    def test_delete_returns_false_when_file_missing(self):
        """delete() returns False when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a file path that doesn't exist
            storage = TokenStorage(f"{tmpdir}/nonexistent.json")

            result = storage.delete()

            assert result is False

    def test_exists_returns_true_when_file_exists(
        self, temp_token_file, sample_token_data
    ):
        """exists() returns True when token file exists."""
        storage = TokenStorage(temp_token_file)
        storage.save(sample_token_data)

        assert storage.exists() is True

    def test_exists_returns_false_when_file_missing(self):
        """exists() returns False when token file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a file path that doesn't exist
            storage = TokenStorage(f"{tmpdir}/nonexistent.json")

            assert storage.exists() is False

    def test_save_and_load_roundtrip(self, temp_token_file, sample_token_data):
        """Tokens can be saved and loaded successfully."""
        storage = TokenStorage(temp_token_file)

        # Save
        storage.save(sample_token_data)

        # Load
        loaded = storage.load()

        assert loaded is not None
        assert loaded.access_token == sample_token_data.access_token
        assert loaded.refresh_token == sample_token_data.refresh_token
        assert loaded.token_type == sample_token_data.token_type
        assert loaded.expires_in == sample_token_data.expires_in
        assert loaded.scope == sample_token_data.scope
        assert loaded.issued_at == sample_token_data.issued_at
