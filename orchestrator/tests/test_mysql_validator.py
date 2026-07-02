from __future__ import annotations

from app.models import CommandResult
from app.validators.mysql_check import _mysqladmin_availability


def test_mysqladmin_alive_stdout_is_available():
    success, detail = _mysqladmin_availability(
        CommandResult(
            command="mysqladmin ping --connect-timeout=5",
            exit_code=0,
            stdout="mysqld is alive\n",
            stderr="",
        )
    )

    assert success is True
    assert "server is alive" in detail


def test_mysqladmin_access_denied_means_server_is_reachable():
    success, detail = _mysqladmin_availability(
        CommandResult(
            command="mysqladmin ping --connect-timeout=5",
            exit_code=0,
            stdout="",
            stderr=(
                "mysqladmin: connect to server at 'localhost' failed\n"
                "error: 'Access denied for user 'appuser'@'localhost' (using password: NO)'\n"
            ),
        )
    )

    assert success is True
    assert "server rejected authentication" in detail


def test_mysqladmin_connection_failure_is_not_available():
    success, detail = _mysqladmin_availability(
        CommandResult(
            command="mysqladmin ping --connect-timeout=5",
            exit_code=1,
            stdout="",
            stderr="Can't connect to local server through socket\n",
        )
    )

    assert success is False
    assert detail == "exit_code=1"
