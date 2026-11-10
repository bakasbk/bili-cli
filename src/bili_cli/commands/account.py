"""bili account: manage several named Bilibili accounts on one machine.

Each account lives in its own directory (the same per-directory isolation that
BILI_CLI_HOME provides). This command group is just a registry on top of that:
`use` points the default `home()` at an account's directory. It never iterates
over accounts or runs anything concurrently -- multi-account automation is
out of scope (see DISCLAIMER.md).
"""

from __future__ import annotations

import os

import typer

from .. import config
from ..errors import BiliError
from ..runtime import run

app = typer.Typer(
    help="管理本机多个命名的 B 站账号：每个账号一个独立目录，互相隔离。`use` 切换默认账号。",
    no_args_is_help=True,
)


def _active_name() -> str | None:
    return config.load_registry().get("default")


@app.command("add")
def add(
    name: str = typer.Argument(..., help="账号名称，作为切换时的标识，如 alt / main。"),
    home: str | None = typer.Option(None, "--home", help="账号目录；留空则在默认配置目录下自动建 accounts/<name>。"),
) -> None:
    """登记一个账号目录。不要求已登录；登录成功后会自动补全 mid / 昵称。"""

    async def body():
        if " " in name or "/" in name or "\\" in name:
            raise BiliError("invalid_argument", "账号名不能包含空格或路径分隔符。")
        reg = config.register_account(name, home)
        return {"added": name, "default": reg.get("default"), "next": f"切换到它：`bili account use {name}`；或直接 `bili auth login` 在当前选中账号下登录。"}

    run(body)


@app.command("list")
def list_() -> None:
    """列出所有账号、当前选中的账号，以及各自的登录态（轻量探测，不刷新凭证）。"""

    async def body():
        reg = config.load_registry()
        accounts = reg.get("accounts", {})
        active = reg.get("default")
        env_home = os.environ.get("BILI_CLI_HOME")
        rows = []
        for nm, acct in accounts.items():
            row = {"name": nm, "home": acct.get("home"), "mid": acct.get("mid"), "display_name": acct.get("name")}
            try:
                with config.env_home_override(acct.get("home")):
                    cred = config.load_credential()
                    row["logged_in"] = bool(cred and cred.sessdata)
            except Exception:
                row["logged_in"] = None
            if nm == active:
                row["active"] = True
            rows.append(row)
        out: dict = {"accounts": rows}
        if env_home:
            out["override"] = "BILI_CLI_HOME 已设置，当前所有命令都作用于该目录，账号切换暂不起作用。"
        elif active:
            out["active"] = active
        else:
            out["hint"] = "还没有选中任何账号，运行 `bili account use <name>` 或 `bili account add <name>`。"
        return out

    run(body)


@app.command("use")
def use(name: str = typer.Argument(..., help="要切换为默认的账号名。")) -> None:
    """切换默认账号；之后不带 BILI_CLI_HOME 的命令都作用于它。"""

    async def body():
        config.select_account(name)
        acct = config.load_registry()["accounts"][name]
        return {"active": name, "home": acct.get("home"), "next": "之后的 `bili auth status` / 各命令都作用于该账号。"}

    run(body)


@app.command("remove")
def remove(
    name: str = typer.Argument(..., help="要移除的账号名。"),
    delete: bool = typer.Option(False, "--delete", help="连账号目录一起删除（不可恢复，请谨慎）。"),
) -> None:
    """从注册表移除账号；默认只移除登记，保留目录。"""

    async def body():
        acct = config.load_registry()["accounts"].get(name)
        if acct is None:
            raise BiliError("invalid_argument", f"账号「{name}」不存在。")
        if delete:
            import shutil

            d = acct.get("home")
            if d and config.Path(d).exists():
                shutil.rmtree(d, ignore_errors=True)
        reg = config.unregister_account(name)
        return {"removed": name, "default_now": reg.get("default"), "directory_deleted": bool(delete)}

    run(body)


@app.command("rename")
def rename(
    old: str = typer.Argument(..., help="原账号名。"),
    new: str = typer.Argument(..., help="新账号名。"),
) -> None:
    """重命名一个账号（只改登记名，目录不变）。"""

    async def body():
        reg = config.load_registry()
        if old not in reg["accounts"]:
            raise BiliError("invalid_argument", f"账号「{old}」不存在。")
        if new in reg["accounts"]:
            raise BiliError("invalid_argument", f"账号名「{new}」已存在。")
        if " " in new or "/" in new or "\\" in new:
            raise BiliError("invalid_argument", "账号名不能包含空格或路径分隔符。")
        reg["accounts"][new] = reg["accounts"].pop(old)
        if reg.get("default") == old:
            reg["default"] = new
        config.save_registry(reg)
        return {"renamed": {"from": old, "to": new}, "default": reg.get("default")}

    run(body)
