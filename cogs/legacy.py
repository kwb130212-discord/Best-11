# -*- coding: utf-8 -*-
"""기존 BEST 기능 모듈을 유지하는 어댑터 Cog."""
from __future__ import annotations
import logging
from discord.ext import commands

log = logging.getLogger("best11.legacy")


class LegacyFeaturesCog(commands.Cog):
    """기존 root 모듈은 best_bot의 호환 로더를 통해 등록합니다.

    이 Cog는 legacy 모듈을 제거하지 않고 수명주기만 Cogs 구조에 맞춥니다.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log.info("Legacy feature adapters enabled")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LegacyFeaturesCog(bot))
