"""Override stub functions in sft.env with real Nix-aware implementations."""

from __future__ import annotations

import sft.env as _env_mod


def apply_overrides() -> None:
    """Replace sft.env stub functions with real implementations."""
    _env_mod.find_envrc_dir_local = _find_envrc_dir_local
    _env_mod.find_envrc_dir_remote = _find_envrc_dir_remote
    _env_mod.parse_envrc_flake_path_local = _parse_envrc_flake_path_local
    _env_mod.parse_envrc_flake_path_remote = _parse_envrc_flake_path_remote
    _env_mod.parse_envrc_flake_full_local = _parse_envrc_flake_full_local
    _env_mod.parse_envrc_flake_full_remote = _parse_envrc_flake_full_remote
    _env_mod.sync_env_payload = _sync_env_payload
    _env_mod.build_remote_execution_command = _build_remote_execution_command
    _env_mod.find_all_envrc_dirs_local = _find_all_envrc_dirs_local
    _env_mod.find_all_envrc_dirs_remote = _find_all_envrc_dirs_remote
    _env_mod.find_project_root = _find_project_root


# --- Real implementations (from original env.py) ---

import json
import os
import shlex
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple

from sft.config import HostInfo, ParsedTarget
from sft.context import ExecutionContext
from sft.shell import rq as _rq
from sft.ui import Theme


def _find_all_envrc_dirs_local(path: str) -> list:
    """Walk *path* downward, return all directories containing .envrc."""
    skip = {".git", ".direnv", ".venv", "__pycache__", ".mypy_cache", "node_modules"}
    root = Path(path).expanduser().resolve()
    result = []
    for dirpath, dirs, _files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        if (Path(dirpath) / ".envrc").is_file():
            result.append(str(Path(dirpath)))
    return sorted(result)


def _find_all_envrc_dirs_remote(
    target: ParsedTarget,
    ctx: ExecutionContext,
    *,
    allow_dry_run_execute: bool = False,
) -> list:
    """Walk remote target path downward, return all directories with .envrc."""
    assert target.host
    path = target.path
    if not path.startswith("~") and not path.startswith("/"):
        path = f"~/{path}"
    script = textwrap.dedent(
        """
        import os, sys, json
        path = os.path.expanduser(%s)
        path = os.path.abspath(path)
        skip = {".git", ".direnv", ".venv", "__pycache__", ".mypy_cache", "node_modules"}
        result = []
        for dirpath, dirs, _files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in skip]
            if os.path.isfile(os.path.join(dirpath, ".envrc")):
                result.append(dirpath)
        print(json.dumps(sorted(result)))
        """
    ) % json.dumps(path)
    try:
        output = ctx.run_ssh(
            target.host,
            f"python3 - <<'PY'\n{script}\nPY",
            capture=True,
            description=f"Scanning .envrc files in {target.path} on {target.host.name}",
            allow_dry_run_execute=allow_dry_run_execute,
        )
        if output:
            return json.loads(output)
    except (RuntimeError, json.JSONDecodeError):
        pass
    return []


def _find_project_root(path: Optional[str] = None) -> Optional[str]:
    if path is None:
        path = os.getcwd()
    candidate = Path(path).expanduser().resolve()
    while True:
        if (candidate / ".envrc").is_file() or (candidate / ".git").exists():
            return str(candidate)
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None


def _find_flake_root_local(path: str) -> Optional[str]:
    candidate = Path(path)
    while True:
        if (candidate / "flake.nix").is_file():
            return str(candidate)
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None


def _find_flake_root_remote(
    target: ParsedTarget, ctx: ExecutionContext
) -> Optional[str]:
    assert target.host
    script = textwrap.dedent(
        """
        import os, sys
        path = os.path.abspath(%s)
        while True:
            if os.path.isfile(os.path.join(path, "flake.nix")):
                print(path)
                sys.exit(0)
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
        sys.exit(1)
        """
    ) % json.dumps(target.path)
    try:
        result = ctx.run_ssh(
            target.host,
            f"python3 - <<'PY'\n{script}\nPY",
            capture=True,
            allow_dry_run_execute=True,
        )
        return result if result else None
    except RuntimeError:
        return None


def _find_envrc_dir_local(path: str) -> Optional[str]:
    candidate = Path(path).expanduser().resolve()
    while True:
        if (candidate / ".envrc").is_file():
            return str(candidate)
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None


def _find_envrc_dir_remote(
    target: ParsedTarget,
    ctx: ExecutionContext,
    *,
    allow_dry_run_execute: bool = False,
) -> Optional[str]:
    assert target.host
    path = target.path
    if not path.startswith("~") and not path.startswith("/"):
        path = f"~/{path}"
    script = textwrap.dedent(
        """
        import os, sys
        path = os.path.expanduser(%s)
        path = os.path.abspath(path)
        while True:
            if os.path.isfile(os.path.join(path, ".envrc")):
                print(path)
                sys.exit(0)
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
        sys.exit(1)
        """
    ) % json.dumps(path)
    try:
        result = ctx.run_ssh(
            target.host,
            f"python3 - <<'PY'\n{script}\nPY",
            capture=True,
            allow_dry_run_execute=allow_dry_run_execute,
        )
        return result if result else None
    except RuntimeError:
        return None


def _parse_envrc_flake_path_local(envrc_dir: str) -> Optional[str]:
    envrc_path = os.path.join(envrc_dir, ".envrc")
    try:
        with open(envrc_path, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("use flake"):
                    tokens = stripped.split()
                    if len(tokens) >= 3:
                        return tokens[2]
    except (OSError, IOError):
        pass
    return None


def _parse_envrc_flake_path_remote(
    target: ParsedTarget,
    envrc_dir: str,
    ctx: ExecutionContext,
) -> Optional[str]:
    assert target.host
    envrc_path = os.path.join(envrc_dir, ".envrc")
    try:
        content = ctx.run_ssh(
            target.host,
            f"cat {_rq(envrc_path)}",
            capture=True,
            allow_dry_run_execute=True,
        )
        if content:
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("use flake"):
                    tokens = stripped.split()
                    if len(tokens) >= 3:
                        return tokens[2]
    except RuntimeError:
        pass
    return None


def _parse_envrc_flake_full_local(envrc_dir: str) -> Optional[Tuple[str, List[str]]]:
    envrc_path = os.path.join(envrc_dir, ".envrc")
    try:
        with open(envrc_path, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("use flake"):
                    tokens = stripped.split()
                    if len(tokens) >= 3:
                        flake_path = tokens[2]
                        extra_flags = [t for t in tokens[3:] if t.startswith("-")]
                        return (flake_path, extra_flags)
    except (OSError, IOError):
        pass
    return None


def _parse_envrc_flake_full_remote(
    target: ParsedTarget,
    envrc_dir: str,
    ctx: ExecutionContext,
) -> Optional[Tuple[str, List[str]]]:
    assert target.host
    envrc_path = os.path.join(envrc_dir, ".envrc")
    try:
        content = ctx.run_ssh(
            target.host,
            f"cat {_rq(envrc_path)}",
            capture=True,
            allow_dry_run_execute=True,
        )
        if content:
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("use flake"):
                    tokens = stripped.split()
                    if len(tokens) >= 3:
                        flake_path = tokens[2]
                        extra_flags = [t for t in tokens[3:] if t.startswith("-")]
                        return (flake_path, extra_flags)
    except RuntimeError:
        pass
    return None


def _sync_env_payload(
    env_source,
    host_info: HostInfo,
    remote_project_dir: str,
    sync_mode: str,
    ctx: ExecutionContext,
) -> Optional[str]:
    if sync_mode == "none":
        return None

    remote_envrc = os.path.join(remote_project_dir, ".envrc")
    remote_flake_dir = None

    if env_source.envrc_dir:
        if ctx.dry_run:
            ctx.log(
                f"Dry-run: sync .envrc -> {host_info.name}:{remote_envrc}",
                always=True,
            )
        else:
            from sft.env import ensure_remote_parent
            ensure_remote_parent(host_info, remote_envrc, ctx)
            ctx.scp_to_remote(
                os.path.join(env_source.envrc_dir, ".envrc"),
                host_info,
                remote_envrc,
            )
            ctx.log(f"Synced .envrc to {host_info.name}:{remote_envrc}")

    if (
        env_source.flake_path
        and env_source.envrc_dir
        and sync_mode in ("full-flake", "stub")
    ):
        local_flake = os.path.expanduser(env_source.flake_path)
        if not os.path.exists(local_flake):
            Theme.warning(f"Local flake path not found: {local_flake}")
            return None

        from sft.env import compute_remote_flake_dir
        remote_flake_dir = compute_remote_flake_dir(
            env_source.envrc_dir,
            env_source.project_root,
            remote_project_dir,
        )

        if sync_mode == "stub":
            Theme.step(Theme.XFER, "Syncing flake stubs", remote_flake_dir)
            for stub in ("flake.nix", "flake.lock"):
                src_file = os.path.join(local_flake, stub)
                if not os.path.exists(src_file):
                    Theme.warning(f"Flake file not found: {src_file}")
                    continue
                dst_file = os.path.join(remote_flake_dir, stub)
                if ctx.dry_run:
                    ctx.log(
                        f"Dry-run: sync {stub} -> {host_info.name}:{dst_file}",
                        always=True,
                    )
                else:
                    from sft.env import ensure_remote_parent
                    ensure_remote_parent(host_info, dst_file, ctx)
                    ctx.scp_to_remote(src_file, host_info, dst_file)
                    ctx.log(f"Synced {stub} to {host_info.name}:{dst_file}")
        else:
            Theme.step(Theme.XFER, "Syncing flake directory", local_flake)
            excludes = [
                ".git", ".direnv", ".venv", "result",
                "__pycache__", "*.pyc", ".mypy_cache",
            ]
            exclude_args = []
            for exc in excludes:
                exclude_args.extend(["--exclude", exc])
            ssh_cmd_parts = (
                ["ssh", "-p", str(host_info.port)]
                + ctx._ssh_options(host_info)
            )
            ssh_full = " ".join(shlex.quote(p) for p in ssh_cmd_parts)
            rsync_cmd = [
                "rsync", "-az", "--partial", "--info=progress2",
            ] + exclude_args + [
                "-e", ssh_full,
                f"{local_flake}/",
                f"{host_info.ssh_target()}:{remote_flake_dir}/",
            ]
            if ctx.dry_run:
                ctx.log(
                    f"Dry-run: rsync {local_flake}/ -> {host_info.name}:{remote_flake_dir}/",
                    always=True,
                )
            else:
                from sft.env import ensure_remote_parent
                ensure_remote_parent(host_info, remote_flake_dir + "/", ctx)
                ctx.log(f"Syncing flake directory to {host_info.name}:{remote_flake_dir}")
                ctx.run(rsync_cmd, description=f"Sync flake to {host_info.name}")

    return remote_flake_dir


def _build_remote_execution_command(
    remote_cwd: str,
    user_command: str,
    env_exports: str,
    auto_env: bool,
    remote_flake_dir: Optional[str],
    flake_flags: Optional[List[str]] = None,
    build_timeout: int = 0,
) -> str:
    inner = f"cd {_rq(remote_cwd)} && {env_exports}{user_command}"
    if auto_env and remote_flake_dir:
        flags_str = " ".join(shlex.quote(f) for f in (flake_flags or []))
        if flags_str:
            flags_str = " " + flags_str
        script_path = f"$HOME/.local/state/sft/tmp-cmd-$$.sh"
        timeout_prefix = ""
        if build_timeout > 0:
            timeout_prefix = f"timeout {build_timeout} "
        nix_cmd = (
            f"mkdir -p \"$(dirname {script_path})\" && "
            f"cat > \"{script_path}\" << 'SFT_SCRIPT_EOF'\n"
            f"{inner}\n"
            f"SFT_SCRIPT_EOF\n"
            f"{timeout_prefix}nix develop{flags_str} {_rq(remote_flake_dir)} "
            f"--command bash \"{script_path}\"; "
            f"rc=$?; rm -f \"{script_path}\"; "
            f"if [ $rc -eq 124 ]; then "
            f"echo 'sft: nix develop timed out after {build_timeout}s' >&2; "
            f"echo 'sft: consider running nix develop manually to pre-cache' >&2; "
            f"fi; "
            f"exit $rc"
        )
        return nix_cmd
    return inner
