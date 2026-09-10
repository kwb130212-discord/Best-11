# -*- coding: utf-8 -*-
"""BEST-11 전역 Discord UI 테마.
기존 기능을 건드리지 않고 Embed 기반 UI를 일관된 프리미엄 스타일로 정리합니다.
"""
import discord
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
PRIMARY = discord.Color.from_rgb(88, 101, 242)
SUCCESS = discord.Color.from_rgb(46, 204, 113)
WARNING = discord.Color.from_rgb(241, 196, 15)
DANGER = discord.Color.from_rgb(237, 66, 69)
DARK = discord.Color.from_rgb(35, 39, 42)


def install_embed_theme():
    """discord.Embed의 기본값만 보강해 기존 임베드를 전역적으로 고급화합니다."""
    if getattr(discord.Embed, "_best11_themed", False):
        return

    original_init = discord.Embed.__init__

    def themed_init(self, *, colour=discord.Embed.Empty, color=discord.Embed.Empty,
                    title=discord.Embed.Empty, type=discord.Embed.Empty,
                    url=discord.Embed.Empty, description=discord.Embed.Empty,
                    timestamp=discord.Embed.Empty):
        if colour is discord.Embed.Empty and color is discord.Embed.Empty:
            color = PRIMARY
        if timestamp is discord.Embed.Empty:
            timestamp = datetime.now(KST)
        original_init(
            self,
            colour=colour,
            color=color,
            title=title,
            type=type,
            url=url,
            description=description,
            timestamp=timestamp,
        )
        self._best11_themed = True

    discord.Embed.__init__ = themed_init
    discord.Embed._best11_themed = True


def brand(embed, section="BEST-11"):
    """푸터 브랜딩을 명시적으로 적용합니다."""
    embed.set_footer(text=f"BEST-11  •  {section}")
    return embed


def success(title, description, section="시스템"):
    return brand(discord.Embed(title=f"✅ {title}", description=description, color=SUCCESS), section)


def warning(title, description, section="시스템"):
    return brand(discord.Embed(title=f"⚠️ {title}", description=description, color=WARNING), section)


def error(title, description, section="시스템"):
    return brand(discord.Embed(title=f"❌ {title}", description=description, color=DANGER), section)


def panel(title, description, section="BEST-11"):
    return brand(discord.Embed(title=title, description=description, color=PRIMARY), section)
