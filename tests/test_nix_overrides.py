"""Tests for sft_nix._overrides — Nix-aware implementations of sft.env stubs.

These tests verify the real implementations that replace the core stubs
when sft-nix is installed.
"""

from __future__ import annotations

import os
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
