# -*- coding: utf-8 -*-
"""BEST 서버 보안/레이드 방어 기능."""
import time
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands

KST = timezone(timedelta(hours=9))
SPAM_WINDOW = 10
SPAM_LIMIT = 8


def setup_security_guard(bot, get_conn, admin_only):
    def init_db():
        c = get_conn()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS security_settings (
            guild_id INTEGER PRIMARY KEY,
            log_channel_id INTEGER,
            raid_threshold INTEGER NOT NULL DEFAULT 5,
            raid_window INTEGER NOT NULL DEFAULT 30,
            raid_timeout INTEGER NOT NULL DEFAULT 10,
            raid_lock_until REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS security_join_events (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at REAL NOT NULL
        );
        """)
        c.commit()
        c.close()

    init_db()
    join_events = defaultdict(deque)
    message_events = defaultdict(deque)

    def get_settings(guild_id):
        c = get_conn()
        row = c.execute("SELECT * FROM security_settings WHERE guild_id=?", (guild_id,)).fetchone()
        if row is None:
            c.execute("INSERT INTO security_settings(guild_id) VALUES(?)", (guild_id,))
            c.commit()
            row = c.execute("SELECT * FROM security_settings WHERE guild_id=?", (guild_id,)).fetchone()
        c.close()
        return row

    async def send_security_log(guild, title, description, color=None):
        row = get_settings(guild.id)
        channel_id = row["log_channel_id"] if row else None
        if not channel_id:
            c = get_conn()
            old = c.execute("SELECT log_channel_id FROM guild_settings WHERE guild_id=?", (guild.id,)).fetchone()
            c.close()
            channel_id = old["log_channel_id"] if old else None
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        embed = discord.Embed(
            title=title,
            description=description,
            color=color or discord.Color.orange(),
            timestamp=datetime.now(KST),
        )
        embed.set_footer(text="BEST • 보안 로그")
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @bot.tree.command(name="보안로그설정", description="[관리자] 보안/레이드 로그 채널을 설정합니다.")
    @app_commands.describe(channel="보안 로그를 보낼 텍스트 채널")
    @admin_only()
    async def set_security_log(interaction: discord.Interaction, channel: discord.TextChannel):
        c = get_conn()
        c.execute(
            "INSERT INTO security_settings(guild_id, log_channel_id) VALUES(?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET log_channel_id=excluded.log_channel_id",
            (interaction.guild_id, channel.id),
        )
        c.commit()
        c.close()
        await interaction.response.send_message(f"✅ 보안 로그 채널을 {channel.mention}으로 설정했습니다.", ephemeral=True)

    @bot.tree.command(name="레이드방어설정", description="[관리자] 대량 입장 레이드 방어 기준을 설정합니다.")
    @app_commands.describe(threshold="몇 명 이상 입장하면 레이드로 볼지 (3~20)", seconds="판정 시간 창 (10~120초)", timeout_minutes="레이드 중 신규 입장자 타임아웃 시간 (1~60분)")
    @admin_only()
    async def raid_settings(
        interaction: discord.Interaction,
        threshold: app_commands.Range[int, 3, 20] = 5,
        seconds: app_commands.Range[int, 10, 120] = 30,
        timeout_minutes: app_commands.Range[int, 1, 60] = 10,
    ):
        c = get_conn()
        c.execute(
            "INSERT INTO security_settings(guild_id, raid_threshold, raid_window, raid_timeout) VALUES(?,?,?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET raid_threshold=excluded.raid_threshold, raid_window=excluded.raid_window, raid_timeout=excluded.raid_timeout",
            (interaction.guild_id, threshold, seconds, timeout_minutes),
        )
        c.commit()
        c.close()
        await interaction.response.send_message(
            f"🛡️ 레이드 방어 설정 완료\n• 기준: **{threshold}명 / {seconds}초**\n• 신규 입장자 타임아웃: **{timeout_minutes}분**",
            ephemeral=True,
        )

    @bot.tree.command(name="보안상태", description="현재 서버 보안/레이드 방어 상태를 확인합니다.")
    async def security_status(interaction: discord.Interaction):
        row = get_settings(interaction.guild_id)
        locked = float(row["raid_lock_until"] or 0) > time.time()
        remain = max(0, int(float(row["raid_lock_until"] or 0) - time.time()))
        e = discord.Embed(
            title="🛡️ BEST 서버 보안 상태",
            color=discord.Color.red() if locked else discord.Color.green(),
        )
        e.add_field(name="레이드 방어", value="🚨 작동 중" if locked else "🟢 대기 중", inline=True)
        e.add_field(name="판정 기준", value=f"{row['raid_threshold']}명 / {row['raid_window']}초", inline=True)
        e.add_field(name="신규 타임아웃", value=f"{row['raid_timeout']}분", inline=True)
        if locked:
            e.add_field(name="남은 보호 시간", value=f"약 {remain}초", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    async def security_member_join(member: discord.Member):
        guild = member.guild
        if member.bot:
            return
        now_ts = time.time()
        row = get_settings(guild.id)
        threshold = int(row["raid_threshold"])
        window = int(row["raid_window"])
        timeout_minutes = int(row["raid_timeout"])

        q = join_events[guild.id]
        q.append(now_ts)
        while q and q[0] < now_ts - window:
            q.popleft()

        c = get_conn()
        c.execute("INSERT INTO security_join_events(guild_id,user_id,joined_at) VALUES(?,?,?)", (guild.id, member.id, now_ts))
        c.execute("DELETE FROM security_join_events WHERE guild_id=? AND joined_at<?", (guild.id, now_ts - 300))
        c.commit()
        c.close()

        raid = len(q) >= threshold
        if raid:
            lock_until = now_ts + max(60, timeout_minutes * 60)
            c = get_conn()
            c.execute("UPDATE security_settings SET raid_lock_until=? WHERE guild_id=?", (lock_until, guild.id))
            c.commit()
            c.close()
            try:
                await member.timeout(
                    discord.utils.utcnow() + timedelta(minutes=timeout_minutes),
                    reason="자동 레이드 방어: 단시간 대량 입장 감지",
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            await send_security_log(
                guild,
                "🚨 레이드 방어 발동",
                f"**{len(q)}명**이 최근 **{window}초** 안에 입장했습니다.\n"
                f"대상: {member.mention} (`{member}`)\n"
                f"조치: 신규 입장자 **{timeout_minutes}분 타임아웃**",
                discord.Color.red(),
            )
        elif float(row["raid_lock_until"] or 0) > now_ts:
            try:
                await member.timeout(
                    discord.utils.utcnow() + timedelta(minutes=timeout_minutes),
                    reason="레이드 보호 모드 중 신규 입장",
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            await send_security_log(guild, "🛡️ 레이드 보호 모드", f"신규 입장자 {member.mention}에게 임시 타임아웃을 적용했습니다.")

    async def security_message(message: discord.Message):
        if message.author.bot or not message.guild:
            return
        key = (message.guild.id, message.author.id)
        now_ts = time.time()
        q = message_events[key]
        q.append(now_ts)
        while q and q[0] < now_ts - SPAM_WINDOW:
            q.popleft()
        if len(q) >= SPAM_LIMIT:
            q.clear()
            try:
                await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=5), reason="자동 도배 방어")
            except (discord.Forbidden, discord.HTTPException):
                return
            await send_security_log(
                message.guild,
                "🚨 도배 방어 발동",
                f"대상: {message.author.mention}\n채널: {message.channel.mention}\n"
                f"조치: **5분 타임아웃**\n기준: {SPAM_LIMIT}회 / {SPAM_WINDOW}초",
                discord.Color.red(),
            )

    async def security_interaction(interaction: discord.Interaction):
        if interaction.guild is None or interaction.type != discord.InteractionType.application_command:
            return
        data = interaction.data or {}
        command_name = data.get("name", "") if isinstance(data, dict) else ""
        if command_name not in {"경고", "경고삭제", "경고초기화"}:
            return
        options = data.get("options", []) if isinstance(data, dict) else []
        details = []
        for option in options:
            if isinstance(option, dict):
                details.append(f"{option.get('name')}: `{option.get('value')}`")
        await send_security_log(
            interaction.guild,
            "⚠️ 경고 관리 로그",
            f"담당 관리자: {interaction.user.mention}\n명령어: `/{command_name}`\n" + ("\n".join(details) if details else "세부 옵션 없음"),
            discord.Color.orange(),
        )

    # 기존 app.py의 이벤트 핸들러를 덮어쓰지 않고 병렬 리스너로 등록합니다.
    bot.add_listener(security_member_join, "on_member_join")
    bot.add_listener(security_message, "on_message")
    bot.add_listener(security_interaction, "on_interaction")
