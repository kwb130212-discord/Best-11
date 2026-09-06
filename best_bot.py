# -*- coding: utf-8 -*-
"""BEST 클랜 봇 전용 실행 진입점.

앱 초기화 단계에서 과거의 잘못된 동적 Discord custom_id 데코레이터를
안전하게 보정하고, 스크림 참석 역할을 일관되게 관리합니다.
"""
import sys
import types
from pathlib import Path


def load_app_safely():
    path = Path(__file__).with_name("app.py")
    source = path.read_text(encoding="utf-8")

    # discord.ui.button 데코레이터는 클래스 정의 시점에 평가되므로
    # __init__ 인자인 scrim_id를 custom_id f-string에서 사용할 수 없습니다.
    # 영구 View에 맞는 고정 custom_id로 바꾸고 실제 스크림 ID는 View 인스턴스가 보유합니다.
    replacements = {
        'custom_id=f"scrim_attend_{scrim_id}"': 'custom_id="scrim_attend"',
        'custom_id=f"scrim_absent_{scrim_id}"': 'custom_id="scrim_absent"',
        'custom_id=f"scrim_pending_{scrim_id}"': 'custom_id="scrim_pending"',
    }
    changed = False
    for old, new in replacements.items():
        if old in source:
            source = source.replace(old, new)
            changed = True

    if changed:
        print("[BEST] ScrimVoteView dynamic custom_id compatibility patch applied")

    module = types.ModuleType("app")
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules["app"] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


app = load_app_safely()
from app import bot, get_conn, admin_only, TOKEN

# BEST 서버의 관리자 역할 이름은 정확히 '관리자'로 고정합니다.
app.ADMIN_ROLE_NAME = "관리자"

SCRIM_ROLE_NAME = "정기내전(스크림)참석"


async def ensure_scrim_role_state(interaction):
    """스크림 참석 상태에 따라 전용 역할을 자동 부여/회수합니다."""
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
            role = await guild.create_role(
                name=SCRIM_ROLE_NAME,
                reason="정기내전(스크림) 참석자 역할 자동 생성",
            )
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

setup_best_features(bot, get_conn, admin_only)
setup_overrides(bot, get_conn, admin_only)
setup_youtube_alerts(bot, get_conn, admin_only)

if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit("DISCORD_TOKEN이 설정되지 않았습니다.")
    bot.run(TOKEN)
