# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands
from core.database import connect, get_settings, init_db


class TicketCreateView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🎫 티켓 열기", style=discord.ButtonStyle.primary, custom_id="best11_ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await create_ticket(interaction)


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 티켓 닫기", style=discord.ButtonStyle.danger, custom_id="best11_ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        row = None
        with connect() as conn:
            row = conn.execute("SELECT * FROM ticket_state WHERE channel_id=?", (interaction.channel_id,)).fetchone()
        if not row:
            await interaction.response.send_message("❌ 티켓 채널이 아닙니다.", ephemeral=True)
            return
        settings = get_settings(interaction.guild_id)
        staff_id = settings["ticket_role_id"] if settings else None
        allowed = interaction.user.guild_permissions.administrator or interaction.user.id == row["owner_id"] or (staff_id and interaction.user.get_role(staff_id))
        if not allowed:
            await interaction.response.send_message("❌ 티켓을 닫을 권한이 없습니다.", ephemeral=True)
            return
        with connect() as conn:
            conn.execute("DELETE FROM ticket_state WHERE channel_id=?", (interaction.channel_id,))
            conn.commit()
        await interaction.response.send_message("🔒 티켓을 종료합니다.")
        await interaction.channel.delete(reason=f"티켓 종료: {interaction.user}")


async def create_ticket(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    user = interaction.user
    settings = get_settings(guild.id) if guild else None
    if guild is None or not settings:
        await interaction.response.send_message("❌ 서버 설정이 없습니다. `/전체설정`을 먼저 실행해주세요.", ephemeral=True)
        return
    category = guild.get_channel(settings["ticket_category_id"]) if settings["ticket_category_id"] else None
    staff = guild.get_role(settings["ticket_role_id"]) if settings["ticket_role_id"] else None
    if not isinstance(category, discord.CategoryChannel) or staff is None:
        await interaction.response.send_message("❌ 티켓 카테고리와 티켓 담당 역할을 확인해주세요.", ephemeral=True)
        return
    with connect() as conn:
        existing = conn.execute("SELECT channel_id FROM ticket_state WHERE guild_id=? AND owner_id=?", (guild.id, user.id)).fetchone()
    if existing and guild.get_channel(existing["channel_id"]):
        await interaction.response.send_message(f"⚠️ 이미 티켓이 있습니다: <#{existing['channel_id']}>", ephemeral=True)
        return
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
        staff: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
    }
    channel = await guild.create_text_channel(f"티켓-{user.name}"[:100], category=category, overwrites=overwrites, reason=f"티켓 생성: {user}")
    with connect() as conn:
        conn.execute("INSERT INTO ticket_state(channel_id,guild_id,owner_id,opened_at) VALUES(?,?,?,?)",
                     (channel.id, guild.id, user.id, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    embed = discord.Embed(title="🎫 티켓이 생성되었습니다", description=f"{user.mention} 님의 문의 채널입니다. 담당자가 확인합니다.", color=discord.Color.blurple())
    await channel.send(content=f"{user.mention} <@&{staff.id}>", embed=embed, view=TicketControlView())
    await interaction.response.send_message(f"✅ 티켓 생성 완료: {channel.mention}", ephemeral=True)


class TicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()

    @app_commands.command(name="티켓", description="문의 티켓을 생성합니다.")
    async def ticket(self, interaction: discord.Interaction) -> None:
        await create_ticket(interaction)

    @app_commands.command(name="티켓패널", description="[관리자] 티켓 생성 패널을 전송합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title=f"🎫 {interaction.guild.name} 지원 티켓", description="아래 버튼을 눌러 개인 문의 채널을 생성하세요.", color=discord.Color.green())
        await interaction.channel.send(embed=embed, view=TicketCreateView(self.bot))
        await interaction.response.send_message("✅ 티켓 패널을 생성했습니다.", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.bot.add_view(TicketCreateView(self.bot))
        self.bot.add_view(TicketControlView())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketCog(bot))
