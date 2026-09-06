# -*- coding: utf-8 -*-
"""BEST 클랜 봇 전용 실행 진입점."""
import sys
import types
from pathlib import Path


def load_app_safely():
    path = Path(__file__).with_name("app.py")
    source = path.read_text(encoding="utf-8")
    replacements = {
        'custom_id=f"scrim_attend_{scrim_id}"': 'custom_id="scrim_attend"',
        'custom_id=f"scrim_absent_{scrim_id}"': 'custom_id="scrim_absent"',
        'custom_id=f"scrim_pending_{scrim_id}"': 'custom_id="scrim_pending"',
    }
    for old, new in replacements.items():
        source = source.replace(old, new)

    module = types.ModuleType("app")
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules["app"] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


app = load_app_safely()
from app import bot, get_conn, admin_only, TOKEN

app.ADMIN_ROLE_NAME = "관리자"
SCRIM_ROLE_NAME = "정기내전(스크림)참석"


async def ensure_scrim_role_state(interaction):
    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, app.discord.Member):
        return
    data = getattr(interaction, "data", None) or {}
    custom_id = data.get("custom_id", "") if isinstance(data, dict) else ""
    attend_ids = {"scrim_attend", "best_scrim_apply"}
    change_ids = attend_ids | {"scrim_absent", "scrim_pending", "best_scrim_cancel"}
    if custom_id not in change_ids:
        return
    role = app.discord.utils.get(guild.roles, name=SCRIM_ROLE_NAME)
    if role is None:
        try:
            role = await guild.create_role(name=SCRIM_ROLE_NAME, reason="정기내전(스크림) 참석자 역할 자동 생성")
        except (app.discord.Forbidden, app.discord.HTTPException) as exc:
            print(f"[BEST-SCRIM] role create failed: {exc}")
            return
    try:
        if custom_id in attend_ids:
            await interaction.user.add_roles(role, reason="정기내전(스크림) 참석")
        else:
            await interaction.user.remove_roles(role, reason="정기내전(스크림) 참석 취소/상태 변경")
    except (app.discord.Forbidden, app.discord.HTTPException) as exc:
        print(f"[BEST-SCRIM] role update failed for {interaction.user}: {exc}")


async def scrim_role_listener(interaction):
    if interaction.type == app.discord.InteractionType.component:
        await ensure_scrim_role_state(interaction)


bot.add_listener(scrim_role_listener, "on_interaction")

from best_features import setup_best_features
from best_overrides import setup_overrides
from youtube_alerts import setup_youtube_alerts
from team_shuffle import setup_team_shuffle
from clan_core import setup_clan_core

setup_best_features(bot, get_conn, admin_only)
setup_overrides(bot, get_conn, admin_only)
setup_youtube_alerts(bot, get_conn, admin_only)
setup_team_shuffle(bot, get_conn)
setup_clan_core(bot, get_conn, admin_only)


_sync_done = False


async def force_command_sync():
    """실행 시 슬래시 명령어를 한 번 확실하게 Discord에 등록/갱신합니다."""
    global _sync_done
    if _sync_done:
        return
    _sync_done = True
    try:
        synced = await bot.tree.sync()
        names = [cmd.name for cmd in bot.tree.get_commands()]
        print(f"[BEST-COMMANDS] 로컬 등록: {len(names)}개 / Discord 동기화: {len(synced)}개")
        print("[BEST-COMMANDS] " + ", ".join(names))
    except Exception as exc:
        _sync_done = False
        print(f"[BEST-COMMANDS] 동기화 실패: {type(exc).__name__}: {exc}")


bot.add_listener(force_command_sync, "on_ready")


if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit("DISCORD_TOKEN이 설정되지 않았습니다.")
    bot.run(TOKEN)
