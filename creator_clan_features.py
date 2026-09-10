# -*- coding: utf-8 -*-
"""BEST-11 유튜버/클랜 운영 기능."""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import discord
from discord import app_commands

KST = timezone(timedelta(hours=9))


def setup_creator_clan_features(bot, get_conn, admin_only):
    def init_db():
        conn = get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_announcement_settings (
                guild_id INTEGER PRIMARY KEY,
                video_channel_id INTEGER,
                notice_channel_id INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def valid_url(value):
        try:
            parsed = urlparse(value.strip())
            return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        except ValueError:
            return False

    def clip(value, limit=1024):
        value = (value or "").strip()
        return value if len(value) <= limit else value[: limit - 3] + "..."

    async def resolve_channel(interaction, channel, kind):
        if channel is not None:
            return channel
        conn = get_conn()
        row = conn.execute(
            "SELECT video_channel_id, notice_channel_id FROM creator_announcement_settings WHERE guild_id=?",
            (interaction.guild_id,),
        ).fetchone()
        conn.close()
        channel_id = row["video_channel_id"] if row and kind == "video" else row["notice_channel_id"] if row else None
        return interaction.guild.get_channel(channel_id) if channel_id else interaction.channel

    @bot.tree.command(name="영상공지", description="[관리자] 유튜브/영상 새 소식을 공지합니다.")
    @app_commands.describe(
        링크="영상 URL",
        제목="공지 제목",
        설명="영상 소개 또는 공지 내용",
        채널="전송할 채널 (생략하면 현재/설정 채널)",
        멘션역할="공지와 함께 멘션할 역할 (선택)",
    )
    @admin_only()
    async def video_announcement(
        interaction: discord.Interaction,
        링크: str,
        제목: str,
        설명: str = None,
        채널: discord.TextChannel = None,
        멘션역할: discord.Role = None,
    ):
        if not valid_url(링크):
            return await interaction.response.send_message("❌ 올바른 http/https 영상 링크를 입력하세요.", ephemeral=True)
        target = await resolve_channel(interaction, 채널, "video")
        if target is None:
            return await interaction.response.send_message("❌ 전송할 채널을 찾을 수 없습니다.", ephemeral=True)
        embed = discord.Embed(
            title=f"🎬 {clip(제목, 256)}",
            description=clip(설명 or "새 영상이 업로드되었습니다!", 4096),
            url=링크.strip(),
            color=discord.Color.red(),
            timestamp=datetime.now(KST),
        )
        embed.add_field(name="▶️ 영상 보기", value=f"[영상 열기]({링크.strip()})", inline=False)
        embed.set_footer(text=f"{interaction.guild.name} · 영상 공지")
        content = 멘션역할.mention if 멘션역할 else None
        allowed = discord.AllowedMentions(roles=True) if 멘션역할 else discord.AllowedMentions.none()
        try:
            await target.send(content=content, embed=embed, allowed_mentions=allowed)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ 해당 채널에 메시지를 보낼 권한이 없습니다.", ephemeral=True)
        await interaction.response.send_message(f"✅ {target.mention}에 영상 공지를 게시했습니다.", ephemeral=True)

    @bot.tree.command(name="공지", description="[관리자] 클랜 공지를 임베드로 게시합니다.")
    @app_commands.describe(
        제목="공지 제목",
        내용="공지 내용",
        채널="전송할 채널 (선택)",
        멘션역할="공지와 함께 멘션할 역할 (선택)",
    )
    @admin_only()
    async def clan_notice(
        interaction: discord.Interaction,
        제목: str,
        내용: str,
        채널: discord.TextChannel = None,
        멘션역할: discord.Role = None,
    ):
        target = await resolve_channel(interaction, 채널, "notice")
        if target is None:
            return await interaction.response.send_message("❌ 전송할 채널을 찾을 수 없습니다.", ephemeral=True)
        embed = discord.Embed(
            title=f"📢 {clip(제목, 256)}",
            description=clip(내용, 4096),
            color=discord.Color.blurple(),
            timestamp=datetime.now(KST),
        )
        embed.set_footer(text=f"{interaction.guild.name} · 클랜 공지")
        content = 멘션역할.mention if 멘션역할 else None
        allowed = discord.AllowedMentions(roles=True) if 멘션역할 else discord.AllowedMentions.none()
        try:
            await target.send(content=content, embed=embed, allowed_mentions=allowed)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ 해당 채널에 메시지를 보낼 권한이 없습니다.", ephemeral=True)
        await interaction.response.send_message(f"✅ {target.mention}에 공지를 게시했습니다.", ephemeral=True)

    @bot.tree.command(name="공지채널설정", description="[관리자] 영상 공지와 일반 공지의 기본 채널을 설정합니다.")
    @app_commands.describe(영상채널="영상 공지 기본 채널", 공지채널="일반 공지 기본 채널")
    @admin_only()
    async def set_announcement_channels(
        interaction: discord.Interaction,
        영상채널: discord.TextChannel,
        공지채널: discord.TextChannel,
    ):
        conn = get_conn()
        conn.execute(
            "INSERT INTO creator_announcement_settings(guild_id,video_channel_id,notice_channel_id) VALUES(?,?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET video_channel_id=excluded.video_channel_id, notice_channel_id=excluded.notice_channel_id",
            (interaction.guild_id, 영상채널.id, 공지채널.id),
        )
        conn.commit()
        conn.close()
        await interaction.response.send_message(
            f"✅ 기본 영상 공지: {영상채널.mention}\n✅ 기본 일반 공지: {공지채널.mention}",
            ephemeral=True,
        )

    @bot.tree.command(name="티켓통계", description="[관리자] 현재 열려 있는 티켓 수를 확인합니다.")
    @admin_only()
    async def ticket_stats(interaction: discord.Interaction):
        conn = get_conn()
        rows = conn.execute(
            "SELECT channel_id, owner_id, opened_at FROM ticket_logs WHERE guild_id=? ORDER BY opened_at DESC",
            (interaction.guild_id,),
        ).fetchall()
        conn.close()
        active = [row for row in rows if interaction.guild.get_channel(row["channel_id"])]
        stale = len(rows) - len(active)
        embed = discord.Embed(title="🎫 티켓 현황", color=discord.Color.green(), timestamp=datetime.now(KST))
        embed.add_field(name="열린 티켓", value=f"`{len(active)}개`", inline=True)
        embed.add_field(name="기록만 남은 티켓", value=f"`{stale}개`", inline=True)
        if active:
            lines = []
            for row in active[:20]:
                channel = interaction.guild.get_channel(row["channel_id"])
                lines.append(f"• {channel.mention} · <@{row['owner_id']}>")
            embed.add_field(name="목록", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="티켓기록정리", description="[관리자] 이미 삭제된 티켓의 오래된 기록을 정리합니다.")
    @admin_only()
    async def clean_ticket_logs(interaction: discord.Interaction):
        conn = get_conn()
        rows = conn.execute("SELECT channel_id FROM ticket_logs WHERE guild_id=?", (interaction.guild_id,)).fetchall()
        stale_ids = [row["channel_id"] for row in rows if interaction.guild.get_channel(row["channel_id"]) is None]
        if stale_ids:
            conn.executemany("DELETE FROM ticket_logs WHERE channel_id=?", [(channel_id,) for channel_id in stale_ids])
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"✅ 삭제된 티켓 기록 `{len(stale_ids)}개`를 정리했습니다.", ephemeral=True)

    init_db()
    print("[BEST] 유튜버 영상공지 + 클랜 공지 + 티켓 관리 기능 loaded")
