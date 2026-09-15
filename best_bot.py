# -*- coding: utf-8 -*-
"""BEST-11 launcher: legacy compatibility + automatic Cog discovery."""
from __future__ import annotations

import importlib
import pkgutil
import sys
import types
from pathlib import Path


def load_app_safely():
    path = Path(__file__).with_name("app.py")
    source = path.read_text(encoding="utf-8")
    source = source.replace('custom_id=f"scrim_attend_{scrim_id}"', 'custom_id="scrim_attend"')
    source = source.replace('custom_id=f"scrim_absent_{scrim_id}"', 'custom_id="scrim_absent"')
    source = source.replace('custom_id=f"scrim_pending_{scrim_id}"', 'custom_id="scrim_pending"')
    module = types.ModuleType("app")
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules["app"] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


OPTION_RENAMES = {
    "이벤트ID":"event_id", "스크림ID":"scrim_id", "제목":"title", "설명":"description", "최대참여":"max_entries",
    "역할":"role", "배율":"multiplier", "채널":"channel", "요일":"weekday", "시":"hour", "분":"minute",
    "내용":"content", "개수":"amount", "대상":"member", "사유":"reason", "결과":"result", "경기수":"games",
    "켜기":"enabled", "링크":"url", "멘션역할":"mention_role", "영상채널":"video_channel", "공지채널":"notice_channel",
}


def load_feature_safely(name: str):
    path = Path(__file__).with_name(name + ".py")
    source = path.read_text(encoding="utf-8")
    for old, new in OPTION_RENAMES.items():
        source = source.replace(old, new)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


app = load_app_safely()
from premium_ui import install_embed_theme
install_embed_theme()
from app import bot, get_conn, admin_only, TOKEN

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

# 기존 기능은 호환 로더로 유지합니다.
best_features = load_feature_safely("best_features")
best_overrides = load_feature_safely("best_overrides")
clan_core = load_feature_safely("clan_core")
clan_rank = load_feature_safely("clan_rank")
from youtube_alerts import setup_youtube_alerts
from team_shuffle import setup_team_shuffle
from security_guard import setup_security_guard
from clan_recruitment import setup_clan_recruitment
from best_upgrade import setup_upgrade
from nvidia_judge import setup_nvidia_judge
from creator_clan_features import setup_creator_clan_features
from dashboard_ui import setup_dashboard

best_features.setup_best_features(bot, get_conn, admin_only)
best_overrides.setup_overrides(bot, get_conn, admin_only)
setup_youtube_alerts(bot, get_conn, admin_only)
setup_team_shuffle(bot, get_conn)
setup_security_guard(bot, get_conn, admin_only)
setup_clan_recruitment(bot, admin_only)
clan_core.setup_clan_core(bot, get_conn, admin_only)
clan_rank.setup_clan_rank(bot, get_conn, admin_only)
setup_upgrade(bot, get_conn, admin_only)
setup_nvidia_judge(bot, get_conn)
setup_creator_clan_features(bot, get_conn, admin_only)
setup_dashboard(bot)

# 새 Cogs가 기존 app의 동일 명령을 대체하도록 트리에서 제거합니다.
for command_name in ("티켓", "티켓패널", "인증패널"):
    bot.tree.remove_command(command_name)


async def load_cogs() -> None:
    package = importlib.import_module("cogs")
    for info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        if info.name.rsplit(".", 1)[-1].startswith("_"):
            continue
        try:
            await bot.load_extension(info.name)
            print(f"[BEST-COGS] loaded: {info.name}")
        except Exception:
            print(f"[BEST-COGS] failed: {info.name}")
            raise


async def setup_hook():
    await load_cogs()


# discord.py Bot 인스턴스에 setup_hook을 안전하게 연결합니다.
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
