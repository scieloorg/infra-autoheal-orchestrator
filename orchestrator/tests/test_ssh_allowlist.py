from __future__ import annotations

import pytest

from app.actions.ssh import SSHCommandError, render_allowed_command


def test_render_allowed_command_uses_local_service_name_only():
    assert render_allowed_command("restart_apache", service="httpd") == "sudo systemctl restart httpd"


def test_unknown_command_key_is_rejected():
    with pytest.raises(SSHCommandError):
        render_allowed_command("rm_everything")
