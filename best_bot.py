# -*- coding: utf-8 -*-
"""BEST-11 launcher: app core + modular feature Cogs."""
from __future__ import annotations

import importlib
import pkgutil
import sys
import types
from pathlib import Path

FEATURE_COGS = {
    "best_features", "best_overrides", "best_upgrade", "clan_core", "clan_rank",
    "clan_recruitment", "creator_clan_features", "dashboard_ui", "nvidia_judge",
    "premium_ui", "security_guard", "team_shuffle", "youtube_alerts",
}

OPTION_RENAMES = {
    "이벤트ID": "event_id", "스크림ID": "scrim_id", "제목": "title", "설명": "description",
    "최대참여": "max_entries", "역할": "role", "배율": "multiplier", "채널": "channel",
    "요일": "weekday", "시": "hour", "분": "minute", "내용": "content", "개수": "amount",
    "대상": "member", "사유": "reason", "결과": "result", "경기수": "games", "켜기": "enabled",
    "링크": "url", "멘션역할": "mention_role", "영상채널": "video_channel", "공지채널": "notice_channel",
}


def exec_module(path: Path, name: str, replacements: dict[str, str] | None = None):
    source = path.read_text(encoding="utf-8")
    for old, new in (replacements or {}).items():
        source = source.replace(old, new)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = "cogs"
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def load_app():
    path = Path(__file__).with_name("app.py")
    return exec_module(path, "app", {
        'custom_id=f"scrim_attend_{scrim_id}"': 'custom_id="scrim_attend"',
        'custom_id=f"scrim_absent_{scrim_id}"': 'custom_id="scrim_absent"',
        'custom_id=f"scrim_pending_{scrim_id}"': 'custom_id="scrim_pending"',
    })


app = load_app()
from app import bot, get_conn, admin_only, TOKEN


def load_feature_cog(name: str):
    path = Path(__file__).parent / "cogs" / f"{name}.py"
    return exec_module(path, name, OPTION_RENAMES)


premium_ui = load_feature_cog("premium_ui")
premium_ui.install_embed_theme()

app.ADMIN_ROLE_NAME = "관리자"
SCRIM_ROLE_NAME = "정기내전(스크림)참석"


async def scrim_role_listener(interaction):
    if interaction.type != app.discord.InteractionType.component or not interaction.guild or not isinstance(interaction.user, app.discord.Member):
        return
    custom_id = (getattr(interaction, "data", None) or {}).get("custom_id", "")
    if custom_id not in {"scrim_attend", "scrim_absent", "scrim_pending", "best_scrim_apply", "best_scrim_cancel"}:
        return
    role = app.discord.utils.get(interaction.guild.roles, name=SCRIM_ROLE_NAME)
    if role is None:
        try:
            role = await interaction.guild.create_role(name=SCRIM_ROLE_NAME, reason="스크림 참석 상태 역할 자동 생성")
        except (app.discord.Forbidden, app.discord.HTTPException) as exc:
            print(f"[BEST-SCRIM] role create failed: {exc}")
            return
    try:
        if custom_id in {"scrim_attend", "best_scrim_apply"}:
            await interaction.user.add_roles(role, reason="스크림 참석")
        else:
            await interaction.user.remove_roles(role, reason="스크림 상태 변경")
    except (app.discord.Forbidden, app.discord.HTTPException) as exc:
        print(f"[BEST-SCRIM] role update failed: {exc}")


bot.add_listener(scrim_role_listener, "on_interaction")

FEATURE_SETUPS = {
    "best_features": "setup_best_features",
    "best_overrides": "setup_overrides",
    "youtube_alerts": "setup_youtube_alerts",
    "team_shuffle": "setup_team_shuffle",
    "security_guard": "setup_security_guard",
    "clan_recruitment": "setup_clan_recruitment",
    "clan_core": "setup_clan_core",
    "clan_rank": "setup_clan_rank",
    "best_upgrade": "setup_upgrade",
    "nvidia_judge": "setup_nvidia_judge",
    "creator_clan_features": "setup_creator_clan_features",
    "dashboard_ui": "setup_dashboard",
}

for module_name, setup_name in FEATURE_SETUPS.items():
    module = load_feature_cog(module_name)
    getattr(module, setup_name)(bot, get_conn, admin_only)

for command_name in ("티켓", "티켓패널", "인증패널"):
    bot.tree.remove_command(command_name)


async def load_cogs() -> None:
    package = importlib.import_module("cogs")
    for info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        name = info.name.rsplit(".", 1)[-1]
        if name.startswith("_") or name in FEATURE_COGS:
            continue
        try:
            await bot.load_extension(info.name)
            print(f"[BEST-COGS] loaded: {info.name}")
        except Exception:
            print(f"[BEST-COGS] failed: {info.name}")
            raise


async def setup_hook():
    await load_cogs()


bot.setup_hook = setup_hook
_sync_lock = False


async def sync_commands():
    global _sync_lock
    if _sync_lock:
        return
    _sync_lock = True
    try:
        synced = await bot.tree.sync()
        print(f"[BEST-COMMANDS] synced={len(synced)} local={len(bot.tree.get_commands())}")
    except Exception as exc:
        _sync_lock = False
        print(f"[BEST-COMMANDS] sync failed: {type(exc).__name__}: {exc}")


bot.add_listener(sync_commands, "on_ready")

if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit("DISCORD_TOKEN이 설정되지 않았습니다.")
    bot.run(TOKEN)
