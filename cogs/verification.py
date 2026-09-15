# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import discord
from discord import app_commands
from discord.ext import commands
from core.database import connect, get_settings, init_db


class VerifyModal(discord.ui.Modal, title="🔒 서버 인증"):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=300)
        self.bot = bot
        self.answer = discord.ui.TextInput(label="인증 이미지의 4자리 숫자", placeholder="4자리 숫자 입력", min_length=4, max_length=4)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        row = get_settings(interaction.guild_id)
        if not row or not row["verified_role_id"] or not row["verification_code"]:
            await interaction.response.send_message("❌ 인증 설정이 완전하지 않습니다.", ephemeral=True)
            return
        with connect() as conn:
            state = conn.execute("SELECT expires_at FROM captcha_state WHERE guild_id=? AND user_id=?", (interaction.guild_id, interaction.user.id)).fetchone()
        if not state or state["expires_at"] < time.time():
            await interaction.response.send_message("❌ 인증 시간이 만료되었습니다. 다시 인증하기를 눌러주세요.", ephemeral=True)
            return
        if self.answer.value.strip() != row["verification_code"]:
            await interaction.response.send_message("❌ 인증 코드가 일치하지 않습니다.", ephemeral=True)
            return
        verified = interaction.guild.get_role(row["verified_role_id"])
        unverified = interaction.guild.get_role(row["unverified_role_id"]) if row["unverified_role_id"] else None
        if verified is None:
            await interaction.response.send_message("❌ 인증 역할을 찾을 수 없습니다.", ephemeral=True)
            return
        try:
            if unverified and unverified in interaction.user.roles:
                await interaction.user.remove_roles(unverified, reason="인증 완료")
            if verified not in interaction.user.roles:
                await interaction.user.add_roles(verified, reason="인증 완료")
        except discord.Forbidden:
            await interaction.response.send_message("❌ 봇의 역할 순위 또는 Manage Roles 권한을 확인해주세요.", ephemeral=True)
            return
        with connect() as conn:
            conn.execute("DELETE FROM captcha_state WHERE guild_id=? AND user_id=?", (interaction.guild_id, interaction.user.id))
            conn.commit()
        await interaction.response.send_message(f"✅ 인증 완료! {verified.mention} 역할이 지급되고 미인증 역할은 제거되었습니다.", ephemeral=True)


class VerifyView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="인증하기 🔓", style=discord.ButtonStyle.green, custom_id="best11_verify")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        row = get_settings(interaction.guild_id)
        if not row or not row["verified_role_id"] or not row["verification_code"]:
            await interaction.response.send_message("❌ `/전체설정`에서 인증 역할과 인증코드를 설정해주세요.", ephemeral=True)
            return
        if interaction.user.get_role(row["verified_role_id"]):
            await interaction.response.send_message("이미 인증된 회원입니다.", ephemeral=True)
            return
        with connect() as conn:
            conn.execute("INSERT INTO captcha_state(guild_id,user_id,code,expires_at) VALUES(?,?,?,?) ON CONFLICT(guild_id,user_id) DO UPDATE SET code=excluded.code,expires_at=excluded.expires_at",
                         (interaction.guild_id, interaction.user.id, row["verification_code"], time.time() + 300))
            conn.commit()
        await interaction.response.send_modal(VerifyModal(self.bot))


class VerificationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()

    @app_commands.command(name="인증패널", description="[관리자] 서버 인증 패널을 생성합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def verification_panel(self, interaction: discord.Interaction) -> None:
        row = get_settings(interaction.guild_id)
        if not row or not row["verified_role_id"] or not row["verification_code"]:
            await interaction.response.send_message("❌ `/전체설정`에서 인증 역할과 인증코드를 먼저 설정해주세요.", ephemeral=True)
            return
        embed = discord.Embed(title="🔒 서버 회원 인증", color=discord.Color.blurple())
        embed.description = "인증 이미지의 4자리 숫자를 확인한 뒤 **인증하기**를 눌러 입력하세요.\n인증 성공 시 미인증 역할이 제거되고 인증 역할이 지급됩니다."
        if row["verification_image_url"]:
            embed.set_image(url=row["verification_image_url"])
        else:
            embed.add_field(name="인증 코드", value=f"`{row['verification_code']}`", inline=False)
        await interaction.channel.send(embed=embed, view=VerifyView(self.bot))
        await interaction.response.send_message("✅ 인증 패널을 생성했습니다.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        row = get_settings(member.guild.id)
        if not row or not row["unverified_role_id"]:
            return
        verified = member.guild.get_role(row["verified_role_id"]) if row["verified_role_id"] else None
        unverified = member.guild.get_role(row["unverified_role_id"])
        if verified and verified in member.roles:
            return
        if unverified is None:
            return
        try:
            await member.add_roles(unverified, reason="신규 입장 미인증 역할 자동 지급")
        except discord.Forbidden:
            print(f"[BEST-11] 미인증 역할 지급 권한 부족: guild={member.guild.id} user={member.id}")
        except discord.HTTPException as exc:
            print(f"[BEST-11] 미인증 역할 지급 실패: {exc}")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.bot.add_view(VerifyView(self.bot))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VerificationCog(bot))
