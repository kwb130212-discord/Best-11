# -*- coding: utf-8 -*-
"""BEST 클랜 봇 전용 실행 진입점."""
from app import bot, get_conn, admin_only, TOKEN
from best_features import setup_best_features

setup_best_features(bot, get_conn, admin_only)

if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit("DISCORD_TOKEN이 설정되지 않았습니다.")
    bot.run(TOKEN)
