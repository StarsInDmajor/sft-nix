# sft-nix

[English](README.md) | **中文**

[sft](https://github.com/StarsInDmajor/sft) 的 Nix 环境插件。提供 `.envrc`/`flake.nix` 检测、flake 同步和 `nix develop` 命令包装，确保远程命令在正确的开发环境中执行。

## 功能

安装此插件后，sft 将自动：

1. **检测 Nix 环境** — 从源目录向上查找包含 `use flake` 指令的 `.envrc` 文件
2. **同步 flake 文件** — 将 `.envrc`、`flake.nix` 和 `flake.lock` 复制到远程主机（stub 模式），或同步整个 flake 目录（full 模式）
3. **包装远程命令** — 在用户命令外注入 `nix develop --command`，使其在 Nix devShell 中执行
4. **传输后自动同步** — 每次文件传输后，若检测到 `.envrc`，自动并行同步 `flake.nix` 和 `flake.lock`

## 安装

```bash
pip install git+https://github.com/StarsInDmajor/sft-nix.git
```

NixOS 用户：此插件会与 sft 核心及其他插件一起构建为 `packages.sft`。

## 工作原理

### 插件加载

sft 启动时通过 `importlib.metadata.entry_points(group="sft.plugins")` 发现插件。本插件在 `pyproject.toml` 中注册为 `nix = "sft_nix.hooks"`。

### 桩函数替换

核心 `sft.env` 模块提供默认返回 `None` 的桩函数：

- `find_envrc_dir_local()` / `find_envrc_dir_remote()`
- `parse_envrc_flake_path_local()` / `parse_envrc_flake_path_remote()`
- `sync_env_payload()`
- `build_remote_execution_command()`
- `find_project_root()`

导入时，`_overrides.apply_overrides()` 将这些桩函数替换为 `_overrides.py` 中真正的 Nix 实现。

### 环境同步流程

```
sft sync-run ./project my-server:~/project -- python train.py
  │
  ├── resolve_env_source()        # 从 ./project 向上查找 .envrc
  │   └── find_envrc_dir_local()  # → /home/user/project（找到 .envrc）
  │   └── parse_envrc_flake_path_local()  # → 从 "use flake ." 解析出 "." 或 "./flake"
  │
  ├── sync_env_payload()          # 复制 .envrc + flake 文件到远程
  │   ├── .envrc → my-server:~/project/.envrc
  │   ├── flake.nix → my-server:~/project/.sft/flake-env/project/flake.nix
  │   └── flake.lock → my-server:~/project/.sft/flake-env/project/flake.lock
  │
  └── build_remote_execution_command()  # 包装为 nix develop
      └── nix develop ~/project/.sft/flake-env/project --command bash <tmpscript>
```

### 传输后钩子

每次执行 `sft src dst` 传输后，插件会检查源目录是否存在 `.envrc`。若存在，则并行同步 `flake.nix` 和 `flake.lock` 到目标位置。

## 同步模式

| 模式          | 行为                                                  |
| ------------- | ----------------------------------------------------- |
| `full-flake`  | rsync 整个 flake 目录（排除 `.git`、`.direnv`、`.venv`、`result`） |
| `stub`        | 仅复制 `flake.nix` + `flake.lock`（默认）             |
| `none`        | 跳过所有环境同步                                       |

## 文件结构

```
sft-nix/
├── src/sft_nix/
│   ├── __init__.py          # 导入时应用覆盖
│   ├── hooks.py             # 入口点：注册传输后钩子
│   └── _overrides.py        # sft.env 桩函数的真正实现
├── tests/
├── pyproject.toml
└── README.md
```

## 开发

```bash
# 测试 sft 核心配合
PYTHONPATH=../sft/src:src \
  python3 -c "
from sft_nix._overrides import apply_overrides
apply_overrides()
from sft.env import find_project_root
print(find_project_root('.'))
"

# 测试 envrc 检测
PYTHONPATH=../sft/src:src \
  python3 -c "
from sft_nix._overrides import apply_overrides
apply_overrides()
from sft.env import find_envrc_dir_local
print(find_envrc_dir_local('.'))
"
```

NixOS 开发工作流详见 [sft 主仓库 README](https://github.com/StarsInDmajor/sft)。

## 许可证

MIT
