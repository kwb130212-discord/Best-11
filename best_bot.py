# -*- coding: utf-8 -*-
"""BEST 클랜 봇 전용 실행 진입점."""
import app
from app import bot, get_conn, admin_only, TOKEN
from best_features import setup_best_features
from best_overrides import setup_overrides
from youtube_alerts import setup_youtube_alerts

# BEST 서버의 관리자 역할 이름은 정확히 '관리자'로 고정합니다.
app.ADMIN_ROLE_NAME = "관리자"

setup_best_features(bot, get_conn, admin_only)
setup_overrides(bot, get_conn, admin_only)
setup_youtube_alerts(bot, get_conn, admin_only)

if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit("DISCORD_TOKEN이 설정되지 않았습니다.")
    bot.run(TOKEN)
