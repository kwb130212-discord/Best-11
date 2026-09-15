# -*- coding: utf-8 -*-
"""BEST-11 하드코딩형 클랜 가입 티켓 시스템."""

import asyncio
import discord
from discord import app_commands

# 요청된 티어는 코드에 고정한다.
CLAN_MEMBER_TIERS = {
    "다이야1", "다이야2", "다이야3",
    "오닉스1", "오닉스2", "오닉스3",
    "네메시스", "아크네메시스",
}
FREE_PASS_1ST_TIERS = {"네메시스", "아크네메시스"}
CLAN_MEMBER_ROLE = "클랜원"
FIRST_TEAM_ROLE = "1군"
TICKET_CATEGORY = "클랜 가입 문의"


def normalize_tier(value: str) -> str:
    value = (value or "").strip().replace(" ", "")
    aliases = {
        "다이아1": "다이야1", "다이아2": "다이야2", "다이아3": "다이야3",
        "오닉스1": "오닉스1", "오닉스2": "오닉스2", "오닉스3": "오닉스3",
        "네메시스1": "네메시스", "아크네메시스1": "아크네메시스",
    }
    return aliases.get(value, value)


def setup_clan_recruitment(bot, admin_only):
    async def get_or_create_role(guild, name):
        role = discord.utils.get(guild.roles, name=name)
        if role:
            return role
        try:
            return await guild.create_role(name=name, reason="BEST-11 가입 티켓 자동 역할 생성")
        except (discord.Forbidden, discord.HTTPException):
            return None

    async def send_result_log(guild, user, answers, result):
        channel = discord.utils.get(guild.text_channels, name="가입-로그")
        if not channel:
            try:
                channel = await guild.create_text_channel("가입-로그", reason="BEST-11 가입 티켓 결과 로그")
            except (discord.Forbidden, discord.HTTPException):
                return
        embed = discord.Embed(title="📋 클랜 가입 심사 결과", color=discord.Color.green() if result else discord.Color.orange())
        embed.add_field(name="지원자", value=user.mention, inline=False)
        embed.add_field(name="최대티어", value=answers[0], inline=True)
        embed.add_field(name="현재레벨", value=answers[1], inline=True)
        embed.add_field(name="현재티어", value=answers[2], inline=True)
        embed.add_field(name="마음가짐", value=answers[3][:1000], inline=False)
        embed.add_field(name="처리", value=result or "수동 심사", inline=False)
        await channel.send(embed=embed)

    class RecruitmentModal(discord.ui.Modal, title="BEST-11 클랜 가입 질문"):
        max_tier = discord.ui.TextInput(label="최대티어", placeholder="예: 네메시스 / 오닉스3 / 다이야1", max_length=30)
        level = discord.ui.TextInput(label="현재레벨", placeholder="현재 레벨을 입력하세요", max_length=30)
        current_tier = discord.ui.TextInput(label="현재티어", placeholder="현재 티어를 입력하세요", max_length=30)
        mindset = discord.ui.TextInput(label="마음가짐", placeholder="클랜 활동에 대한 각오/마음가짐", style=discord.TextStyle.paragraph, max_length=1000)

        async def on_submit(self, interaction: discord.Interaction):
            guild = interaction.guild
            if guild is None:
                return await interaction.response.send_message("❌ 서버에서만 사용할 수 있습니다.", ephemeral=True)

            max_tier = normalize_tier(str(self.max_tier.value))
            current_tier = str(self.current_tier.value).strip()
            answers = (max_tier, str(self.level.value).strip(), current_tier, str(self.mindset.value).strip())

            # 중복 티켓 방지
            existing = discord.utils.find(
                lambda c: isinstance(c, discord.TextChannel) and c.topic and f"지원자:{interaction.user.id}" in c.topic,
                guild.text_channels,
            )
            if existing:
                return await interaction.response.send_message(f"⚠️ 이미 가입 티켓이 있습니다: {existing.mention}", ephemeral=True)

            result = None
            roles_to_add = []
            if max_tier in CLAN_MEMBER_TIERS:
                clan_role = await get_or_create_role(guild, CLAN_MEMBER_ROLE)
                if clan_role:
                    roles_to_add.append(clan_role)
                if max_tier in FREE_PASS_1ST_TIERS:
                    first_role = await get_or_create_role(guild, FIRST_TEAM_ROLE)
                    if first_role:
                        roles_to_add.append(first_role)
                    result = "✅ 자동 승인: 클랜원 + 1군 프리패스"
                else:
                    result = "✅ 자동 승인: 클랜원 지급"

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            }
            if guild.me:
                overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
            admin_role = discord.utils.get(guild.roles, name="관리자")
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            category = discord.utils.get(guild.categories, name=TICKET_CATEGORY)
            if category is None:
                try:
                    category = await guild.create_category(TICKET_CATEGORY, reason="BEST-11 클랜 가입 티켓")
                except (discord.Forbidden, discord.HTTPException):
                    category = None

            safe_name = ''.join(ch.lower() if ch.isalnum() else '-' for ch in interaction.user.name)[:20].strip('-') or 'user'
            try:
                ticket = await guild.create_text_channel(
                    f"가입-{safe_name}",
                    category=category,
                    overwrites=overwrites,
                    topic=f"지원자:{interaction.user.id} | 최대티어:{max_tier}",
                    reason="BEST-11 클랜 가입 티켓 생성",
                )
            except (discord.Forbidden, discord.HTTPException) as exc:
                return await interaction.response.send_message(f"❌ 티켓 채널 생성 실패: {exc}", ephemeral=True)

            if roles_to_add:
                try:
                    await interaction.user.add_roles(*roles_to_add, reason=f"클랜 가입 자동 승인: {max_tier}")
                except (discord.Forbidden, discord.HTTPException):
                    result = (result or "심사 대기") + "\n⚠️ 역할 자동 지급에 실패했습니다. 봇 역할 순서를 확인하세요."
            elif max_tier not in CLAN_MEMBER_TIERS:
                result = "🟡 자동 승인 대상 외 티어 → 관리자 수동 심사"

            embed = discord.Embed(title="🎫 BEST-11 클랜 가입 티켓", description="관리자가 확인할 수 있는 가입 문의 채널입니다.", color=discord.Color.blurple())
            embed.add_field(name="🏆 최대티어", value=max_tier, inline=True)
            embed.add_field(name="📈 현재레벨", value=answers[1], inline=True)
            embed.add_field(name="🎖️ 현재티어", value=current_tier, inline=True)
            embed.add_field(name="🧠 마음가짐", value=answers[3][:1000], inline=False)
            embed.add_field(name="⚙️ 자동처리", value=result, inline=False)
            embed.set_footer(text="관리자는 내용을 확인한 뒤 최종 가입 여부를 확인하세요.")
            await ticket.send(content=f"{interaction.user.mention} <@&{admin_role.id}>" if admin_role else interaction.user.mention, embed=embed)
            await interaction.response.send_message(f"✅ 가입 티켓이 생성되었습니다: {ticket.mention}\n{result}", ephemeral=True)
            await send_result_log(guild, interaction.user, answers, result)

    class RecruitmentView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="🎫 클랜 가입 신청", style=discord.ButtonStyle.success, custom_id="best_recruitment_open")
        async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(RecruitmentModal())

    @bot.tree.command(name="가입패널", description="[관리자] BEST-11 클랜 가입 티켓 패널을 생성합니다.")
    @admin_only()
    async def recruitment_panel(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎫 BEST-11 클랜 가입 신청",
            description=(
                "아래 버튼을 눌러 가입 질문에 답변해주세요.\n\n"
                "**질문**\n"
                "1️⃣ 최대티어\n2️⃣ 현재레벨\n3️⃣ 현재티어\n4️⃣ 마음가짐\n\n"
                "**자동 승인 티어**\n"
                "다이야1 · 다이야2 · 다이야3 · 오닉스1 · 오닉스2 · 오닉스3 · 네메시스 · 아크네메시스\n\n"
                "네메시스/아크네메시스는 **1군 프리패스**가 적용됩니다."
            ),
            color=discord.Color.blurple(),
        )
        await interaction.channel.send(embed=embed, view=RecruitmentView())
        await interaction.response.send_message("✅ 가입 패널을 생성했습니다.", ephemeral=True)

    async def register_persistent_view():
        await bot.wait_until_ready()
        bot.add_view(RecruitmentView())

    bot.add_listener(register_persistent_view, "on_ready")
    print("[BEST-RECRUITMENT] 가입 티켓 시스템 로드 완료")
