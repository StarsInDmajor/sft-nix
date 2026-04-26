"""Tests for sft_nix._overrides — Nix-aware implementations of sft.env stubs.

These tests verify the real implementations that replace the core stubs
when sft-nix is installed.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path


class TestFindEnvrcDirLocal(unittest.TestCase):
    """Test _find_envrc_dir_local from sft_nix._overrides."""

    def _apply_overrides(self):
        from sft_nix._overrides import apply_overrides
        apply_overrides()

    def test_finds_envrc_in_subdir(self):
        self._apply_overrides()
        from sft.env import find_envrc_dir_local

        with tempfile.TemporaryDirectory() as tmp:
            envrc_dir = Path(tmp) / "project"
            envrc_dir.mkdir()
            (Path(envrc_dir) / ".envrc").write_text("use flake /some/path")
            result = find_envrc_dir_local(str(envrc_dir))
            self.assertEqual(result, str(envrc_dir))

    def test_no_envrc(self):
        self._apply_overrides()
        from sft.env import find_envrc_dir_local

        with tempfile.TemporaryDirectory() as tmp:
            result = find_envrc_dir_local(str(tmp))
            self.assertIsNone(result)


class TestParseEnvrcFlakeFullLocal(unittest.TestCase):
    """Test _parse_envrc_flake_full_local from sft_nix._overrides."""

    def _apply_overrides(self):
        from sft_nix._overrides import apply_overrides
        apply_overrides()

    def test_parse_flake_with_flags(self):
        self._apply_overrides()
        from sft.env import parse_envrc_flake_full_local

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".envrc").write_text("use flake /some/flake/path --impure\n")
            result = parse_envrc_flake_full_local(str(tmp))
            self.assertEqual(result, ("/some/flake/path", ["--impure"]))

    def test_parse_flake_without_flags(self):
        self._apply_overrides()
        from sft.env import parse_envrc_flake_full_local

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".envrc").write_text("use flake /simple/path\n")
            result = parse_envrc_flake_full_local(str(tmp))
            self.assertEqual(result, ("/simple/path", []))

    def test_no_flake_line(self):
        self._apply_overrides()
        from sft.env import parse_envrc_flake_full_local

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".envrc").write_text("use nix\n")
            result = parse_envrc_flake_full_local(str(tmp))
            self.assertIsNone(result)


class TestParseEnvrcFlakePathLocal(unittest.TestCase):
    """Test _parse_envrc_flake_path_local from sft_nix._overrides."""

    def _apply_overrides(self):
        from sft_nix._overrides import apply_overrides
        apply_overrides()

    def test_returns_path_only(self):
        self._apply_overrides()
        from sft.env import parse_envrc_flake_path_local

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".envrc").write_text("use flake /some/path --impure\n")
            result = parse_envrc_flake_path_local(str(tmp))
            self.assertEqual(result, "/some/path")


class TestBuildRemoteExecutionCommand(unittest.TestCase):
    """Test _build_remote_execution_command from sft_nix._overrides."""

    def _apply_overrides(self):
        from sft_nix._overrides import apply_overrides
        apply_overrides()

    def test_with_env(self):
        self._apply_overrides()
        from sft.env import build_remote_execution_command

        cmd = build_remote_execution_command(
            remote_cwd="~/project",
            user_command="python script.py",
            env_exports="export FOO=bar ",
            auto_env=True,
            remote_flake_dir="/tmp/flake",
            flake_flags=["--impure"],
        )
        self.assertIn("nix develop --impure", cmd)
        self.assertIn("python script.py", cmd)

    def test_without_env(self):
        self._apply_overrides()
        from sft.env import build_remote_execution_command

        cmd = build_remote_execution_command(
            remote_cwd="~/project",
            user_command="python script.py",
            env_exports="",
            auto_env=False,
            remote_flake_dir=None,
        )
        self.assertEqual(cmd, 'cd "$HOME/project" && python script.py')

    def test_env_no_flake_dir(self):
        self._apply_overrides()
        from sft.env import build_remote_execution_command

        cmd = build_remote_execution_command(
            remote_cwd="~/project",
            user_command="echo hello",
            env_exports="",
            auto_env=True,
            remote_flake_dir=None,
        )
        self.assertNotIn("nix develop", cmd)

    def test_with_build_timeout(self):
        self._apply_overrides()
        from sft.env import build_remote_execution_command

        cmd = build_remote_execution_command(
            remote_cwd="~/project",
            user_command="python script.py",
            env_exports="",
            auto_env=True,
            remote_flake_dir="/tmp/flake",
            build_timeout=300,
        )
        self.assertIn("timeout 300 nix develop", cmd)
        self.assertIn("timed out after 300s", cmd)

    def test_without_build_timeout(self):
        self._apply_overrides()
        from sft.env import build_remote_execution_command

        cmd = build_remote_execution_command(
            remote_cwd="~/project",
            user_command="python script.py",
            env_exports="",
            auto_env=True,
            remote_flake_dir="/tmp/flake",
            build_timeout=0,
        )
        self.assertNotIn("timeout", cmd)


class TestFindProjectRoot(unittest.TestCase):
    """Test _find_project_root from sft_nix._overrides (enhanced to find .envrc)."""

    def _apply_overrides(self):
        from sft_nix._overrides import apply_overrides
        apply_overrides()

    def test_finds_git_root(self):
        self._apply_overrides()
        from sft.env import find_project_root

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").mkdir()
            result = find_project_root(str(tmp))
            self.assertEqual(result, str(tmp))

    def test_finds_envrc_root(self):
        self._apply_overrides()
        from sft.env import find_project_root

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".envrc").write_text("use flake")
            result = find_project_root(str(tmp))
            self.assertEqual(result, str(tmp))

    def test_returns_none(self):
        self._apply_overrides()
        from sft.env import find_project_root

        with tempfile.TemporaryDirectory() as tmp:
            result = find_project_root(str(tmp))
            self.assertIsNone(result)


class TestPostTransferEnvrcFlake(unittest.TestCase):
    """Test _post_transfer_envrc_flake hook copies .envrc alongside flake files."""

    def _apply_overrides(self):
        from sft_nix._overrides import apply_overrides
        apply_overrides()

    @unittest.mock.patch("sft.transfer.copy_single_file")
    def test_envrc_copied_on_local_to_local(self, mock_copy):
        """When src is local with .envrc, hook should copy .envrc to dst."""
        self._apply_overrides()
        from sft_nix.hooks import _post_transfer_envrc_flake
        from sft.config import ParsedTarget

        with tempfile.TemporaryDirectory() as tmp:
            # Create source project with .envrc and flake
            src_dir = Path(tmp) / "project"
            src_dir.mkdir()
            (src_dir / ".envrc").write_text("use flake /some/flake/path\n")

            flake_dir = Path(tmp) / "flake"
            flake_dir.mkdir()
            (flake_dir / "flake.nix").write_text("{}")
            (flake_dir / "flake.lock").write_text("{}")

            # Create dest
            dst_dir = Path(tmp) / "dest"
            dst_dir.mkdir()

            src = ParsedTarget(is_remote=False, path=str(src_dir), host=None, user_override=None)
            dst = ParsedTarget(is_remote=False, path=str(dst_dir), host=None, user_override=None)

            ctx = unittest.mock.MagicMock()
            args = unittest.mock.MagicMock()

            _post_transfer_envrc_flake(src, dst, args, ctx)

            # Check that copy_single_file was called for .envrc
            envrc_copies = [
                call for call in mock_copy.call_args_list
                if call[0][1].endswith(".envrc")
            ]
            self.assertTrue(len(envrc_copies) >= 1,
                            f"Expected .envrc copy call, got: {mock_copy.call_args_list}")
            # Verify destination path includes project name (dir-append logic)
            dest_path = envrc_copies[0][0][3]
            self.assertIn("project", dest_path,
                          f"Expected 'project' in dest path, got: {dest_path}")

    @unittest.mock.patch("sft.transfer.copy_single_file")
    def test_no_envrc_no_copy(self, mock_copy):
        """When src has no .envrc, hook should not attempt .envrc copy."""
        self._apply_overrides()
        from sft_nix.hooks import _post_transfer_envrc_flake
        from sft.config import ParsedTarget

        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "project"
            src_dir.mkdir()
            # No .envrc created

            dst_dir = Path(tmp) / "dest"
            dst_dir.mkdir()

            src = ParsedTarget(is_remote=False, path=str(src_dir), host=None, user_override=None)
            dst = ParsedTarget(is_remote=False, path=str(dst_dir), host=None, user_override=None)

            ctx = unittest.mock.MagicMock()
            args = unittest.mock.MagicMock()

            _post_transfer_envrc_flake(src, dst, args, ctx)

            # No .envrc copy should happen
            envrc_copies = [
                call for call in mock_copy.call_args_list
                if call[0][1].endswith(".envrc")
            ]
            self.assertEqual(len(envrc_copies), 0)


if __name__ == "__main__":
    unittest.main()
