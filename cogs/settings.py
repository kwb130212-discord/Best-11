# -*- coding: utf-8 -*-
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from core.database import get_settings, init_db, update_settings


class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()

    @app_commands.command(name="전체설정", description="[관리자] 관리·인증·티켓 설정을 한 번에 저장합니다.")
    @app_commands.describe(
        관리역할="관리 기능 역할", 인증관리역할="인증 설정 관리 역할", 지급역할="역할 지급 기능 역할",
        티켓담당역할="티켓 담당 역할", 미인증역할="입장 시 자동 지급 역할", 인증역할="인증 성공 시 지급 역할",
        티켓카테고리="티켓 생성 카테고리", 로그채널="로그 채널", 인증이미지url="인증 패널 이미지 URL (선택)",
        인증코드="인증 이미지에 적힌 4자리 숫자",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def all_settings(self, interaction: discord.Interaction, 관리역할: discord.Role, 인증관리역할: discord.Role,
                           지급역할: discord.Role, 티켓담당역할: discord.Role, 미인증역할: discord.Role,
                           인증역할: discord.Role, 티켓카테고리: discord.CategoryChannel, 로그채널: discord.TextChannel,
                           인증코드: str, 인증이미지url: str | None = None) -> None:
        code = 인증코드.strip()
        if len(code) != 4 or not code.isdigit():
            await interaction.response.send_message("❌ 인증코드는 정확히 4자리 숫자여야 합니다.", ephemeral=True)
            return
        if 인증역할 >= interaction.guild.me.top_role or 미인증역할 >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ 미인증/인증 역할이 봇의 최고 역할보다 아래에 있어야 합니다.", ephemeral=True)
            return
        update_settings(interaction.guild_id, management_role_id=관리역할.id, auth_role_id=인증관리역할.id,
                        grant_role_id=지급역할.id, ticket_role_id=티켓담당역할.id,
                        unverified_role_id=미인증역할.id, verified_role_id=인증역할.id,
                        ticket_category_id=티켓카테고리.id, log_channel_id=로그채널.id,
                        verification_image_url=(인증이미지url or "").strip() or None, verification_code=code)
        embed = discord.Embed(title="⚙️ 전체 설정 저장 완료", color=discord.Color.green())
        for name, value in (("관리 역할", 관리역할), ("인증 관리", 인증관리역할), ("지급 역할", 지급역할),
                            ("티켓 담당", 티켓담당역할), ("미인증 역할", 미인증역할), ("인증 역할", 인증역할)):
            embed.add_field(name=name, value=value.mention)
        embed.add_field(name="티켓 카테고리", value=티켓카테고리.name)
        embed.add_field(name="로그 채널", value=로그채널.mention)
        embed.add_field(name="인증 이미지", value="설정됨" if 인증이미지url else "없음")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="전체설정확인", description="[관리자] 현재 서버 설정을 확인합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def show_settings(self, interaction: discord.Interaction) -> None:
        row = get_settings(interaction.guild_id)
        if not row:
            await interaction.response.send_message("설정이 없습니다. `/전체설정`을 먼저 실행하세요.", ephemeral=True)
            return
        fields = [("관리 역할", row["management_role_id"]), ("인증 관리 역할", row["auth_role_id"]),
                  ("지급 역할", row["grant_role_id"]), ("티켓 담당 역할", row["ticket_role_id"]),
                  ("미인증 역할", row["unverified_role_id"]), ("인증 역할", row["verified_role_id"]),
                  ("티켓 카테고리", row["ticket_category_id"]), ("로그 채널", row["log_channel_id"])]
        embed = discord.Embed(title="⚙️ 서버 설정", color=discord.Color.blurple())
        for label, value in fields:
            if not value:
                text = "미설정"
            elif "역할" in label:
                text = f"<@&{value}>"
            elif label == "로그 채널":
                text = f"<#${value}>".replace("$", "")
            else:
                text = f"ID `{value}`"
            embed.add_field(name=label, value=text)
        embed.add_field(name="인증 이미지 URL", value=row["verification_image_url"] or "미설정", inline=False)
        embed.add_field(name="인증 코드", value="••••", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
