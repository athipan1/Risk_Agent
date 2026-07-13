from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import Header, HTTPException, status


logger = logging.getLogger(__name__)

DEFAULT_HALT_FILE = '/data/emergency_halt.flag'


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class EmergencyHaltState:
    """Process-local halt state backed by a shared, persistent JSON flag file."""

    def __init__(
        self,
        flag_path: str | Path | None = None,
        default_active: bool | None = None,
    ) -> None:
        self.flag_path = Path(flag_path or os.getenv('EMERGENCY_HALT_FILE', DEFAULT_HALT_FILE))
        self.default_active = (
            _env_bool('EMERGENCY_HALT', False)
            if default_active is None
            else bool(default_active)
        )
        self._lock = threading.RLock()
        self._file_signature: tuple[int, int, int] | None = None
        self._state = self._default_state()
        self._sync_from_disk()

    def _default_state(self) -> dict[str, Any]:
        return {
            'active': self.default_active,
            'reason': 'EMERGENCY_HALT deploy default' if self.default_active else None,
            'updated_at': None,
            'source': 'environment_default',
        }

    def _signature(self) -> tuple[int, int, int] | None:
        try:
            stat_result = self.flag_path.stat()
        except FileNotFoundError:
            return None
        return stat_result.st_ino, stat_result.st_mtime_ns, stat_result.st_size

    def _read_file(self) -> dict[str, Any]:
        with self.flag_path.open(encoding='utf-8') as handle:
            record = json.load(handle)
        if not isinstance(record, dict) or type(record.get('active')) is not bool:
            raise ValueError('halt state file must contain a boolean active field')
        return {
            'active': record['active'],
            'reason': record.get('reason'),
            'updated_at': record.get('updated_at'),
            'source': 'runtime_file',
        }

    def _sync_from_disk(self) -> None:
        with self._lock:
            signature = self._signature()
            if signature == self._file_signature:
                return
            if signature is None:
                self._state = self._default_state()
                self._file_signature = None
                return
            try:
                self._state = self._read_file()
            except (OSError, ValueError, json.JSONDecodeError):
                logger.exception('invalid emergency halt state file; failing closed path=%s', self.flag_path)
                self._state = {
                    'active': True,
                    'reason': 'invalid emergency halt state file; failed closed',
                    'updated_at': _timestamp(),
                    'source': 'runtime_file_error',
                }
            self._file_signature = signature

    def _write_file(self, record: dict[str, Any]) -> None:
        self.flag_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f'.{self.flag_path.name}.',
            dir=self.flag_path.parent,
            text=True,
        )
        try:
            os.chmod(temp_name, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                json.dump(record, handle, separators=(',', ':'), sort_keys=True)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.flag_path)
            self._file_signature = self._signature()
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def is_active(self) -> bool:
        self._sync_from_disk()
        with self._lock:
            return bool(self._state['active'])

    def snapshot(self) -> dict[str, Any]:
        self._sync_from_disk()
        with self._lock:
            return dict(self._state)

    def trip(self, reason: str) -> dict[str, Any]:
        record = {
            'active': True,
            'reason': reason,
            'updated_at': _timestamp(),
            'source': 'runtime_file',
        }
        with self._lock:
            # Trip memory first so this process fails closed even if persistence fails.
            self._state = record
            try:
                self._write_file(record)
            except OSError:
                logger.exception(
                    'emergency halt tripped in memory but persistence failed timestamp=%s reason=%s',
                    record['updated_at'],
                    reason,
                )
                raise
        logger.warning(
            'emergency halt tripped timestamp=%s reason=%s',
            record['updated_at'],
            reason,
        )
        return dict(record)

    def clear(self, reason: str, *, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise ValueError('confirm must be true to clear the emergency halt')
        record = {
            'active': False,
            'reason': reason,
            'updated_at': _timestamp(),
            'source': 'runtime_file',
        }
        with self._lock:
            # Persist a clear before applying it in memory so a write failure stays halted.
            try:
                self._write_file(record)
            except OSError:
                logger.exception(
                    'emergency halt clear persistence failed; remaining halted timestamp=%s reason=%s',
                    record['updated_at'],
                    reason,
                )
                raise
            self._state = record
        logger.info(
            'emergency halt cleared timestamp=%s reason=%s',
            record['updated_at'],
            reason,
        )
        return dict(record)


_STATE = EmergencyHaltState()


def is_emergency_halt_active() -> bool:
    return _STATE.is_active()


def get_emergency_halt_state() -> dict[str, Any]:
    return _STATE.snapshot()


def trip_emergency_halt(reason: str) -> dict[str, Any]:
    return _STATE.trip(reason)


def clear_emergency_halt(reason: str, *, confirm: bool) -> dict[str, Any]:
    return _STATE.clear(reason, confirm=confirm)


def require_admin_token(
    x_admin_token: Annotated[str | None, Header(alias='X-Admin-Token')] = None,
) -> None:
    configured_token = os.getenv('ADMIN_TOKEN')
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='ADMIN_TOKEN is not configured',
        )
    if x_admin_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='X-Admin-Token header is required',
        )
    if not secrets.compare_digest(x_admin_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='invalid admin token',
        )
