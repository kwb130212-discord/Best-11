# -*- coding: utf-8 -*-
"""BEST-11 전용 브랜딩/간편 명령어.

이 모듈은 기존 app.py의 관리자 판정을 '관리자' 역할명으로 맞추고,
루에드 유튜브 브랜딩과 무료 이벤트(무입금) 기능의 편의 명령을 추가한다.
"""

import os
import sqlite3
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands

KST = timezone(timedelta(hours=9))
BOT_NAME = "루에드 유튜브"
ROUED_CHANNEL = os.getenv("ROUED_YOUTUBE_CHANNEL", "https://www.youtube.com/@루에드")


def setup_overrides(bot, get_conn, admin_only):
    def now():
        return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    def ensure_tables():
        c = get_conn()
        c.execute("""
            CREATE TABLE IF NOT EXISTS best_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER,
                title TEXT,
                description TEXT,
                max_entries INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS best_event_entries(
                event_id INTEGER,
                user_id INTEGER,
                user_name TEXT,
                created_at TEXT,
                PRIMARY KEY(event_id,user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS best_role_weights(
                guild_id INTEGER,
                role_id INTEGER,
                multiplier REAL DEFAULT 1.0,
                PRIMARY KEY(guild_id,role_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS best_yt_subs(
                guild_id INTEGER,
                user_id INTEGER,
                channel_ref TEXT,
                channel_id TEXT,
                last_video_id TEXT,
                PRIMARY KEY(guild_id,user_id,channel_ref)
            )
        """)
        c.commit()
        c.close()

    ensure_tables()

    def multiplier(member):
        c = get_conn()
        rows = c.execute(
            "SELECT role_id,multiplier FROM best_role_weights WHERE guild_id=?",
            (member.guild.id,)
        ).fetchall()
        c.close()
        return max(
            [float(r["multiplier"]) for r in rows if any(role.id == r["role_id"] for role in member.roles)]
            + [1.0]
        )

    class EventView(discord.ui.View):
        def __init__(self, event_id):
            super().__init__(timeout=None)
            self.event_id = event_id

        @discord.ui.button(label="🎟️ 이벤트 참여", style=discord.ButtonStyle.success, custom_id="roued_event_join")
        async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
            c = get_conn()
            event = c.execute(
                "SELECT * FROM best_events WHERE id=? AND guild_id=? AND active=1",
                (self.event_id, interaction.guild_id),
            ).fetchone()
            if not event:
                c.close()
                return await interaction.response.send_message("❌ 종료되었거나 존재하지 않는 이벤트입니다.", ephemeral=True)
            count = c.execute(
                "SELECT COUNT(*) AS n FROM best_event_entries WHERE event_id=?",
                (self.event_id,),
            ).fetchone()["n"]
            if c.execute(
                "SELECT 1 FROM best_event_entries WHERE event_id=? AND user_id=?",
                (self.event_id, interaction.user.id),
            ).fetchone():
                c.close()
                return await interaction.response.send_message("⚠️ 이미 참여했습니다.", ephemeral=True)
            if event["max_entries"] and count >= event["max_entries"]:
                c.close()
                return await interaction.response.send_message("❌ 참여 인원이 가득 찼습니다.", ephemeral=True)
            c.execute(
                "INSERT INTO best_event_entries VALUES(?,?,?,?)",
                (self.event_id, interaction.user.id, interaction.user.display_name, now()),
            )
            c.commit()
            c.close()
            await interaction.response.send_message("✅ 이벤트 참여 완료!", ephemeral=True)

        @discord.ui.button(label="🎲 내 가중치", style=discord.ButtonStyle.primary, custom_id="roued_event_weight")
        async def show_weight(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message(
                f"🎲 현재 무료 이벤트 당첨 가중치: **{multiplier(interaction.user):.2f}배**",
                ephemeral=True,
            )

    @bot.tree.command(name="이벤트", description="[관리자] 물품과 주최자를 지정해 무료 이벤트를 생성합니다.")
    @app_commands.describe(
        물품="이벤트로 제공할 물품/보상 이름",
        주최자="이벤트 주최자",
        설명="이벤트 안내",
        최대참여="0이면 제한 없음",
    )
    @admin_only()
    async def event_command(
        interaction: discord.Interaction,
        물품: str,
        주최자: discord.Member,
        설명: str = "",
        최대참여: int = 0,
    ):
        if 최대참여 < 0:
            return await interaction.response.send_message("❌ 최대참여는 0 이상이어야 합니다.", ephemeral=True)
        c = get_conn()
        cur = c.cursor()
        cur.execute(
            "INSERT INTO best_events(guild_id,channel_id,title,description,max_entries,created_at) VALUES(?,?,?,?,?,?)",
            (interaction.guild_id, interaction.channel_id, 물품, 설명, 최대참여, now()),
        )
        event_id = cur.lastrowid
        c.commit()
        c.close()

        embed = discord.Embed(
            title="🎁 루에드 유튜브 | BEST 이벤트",
            description=설명 or "아래 버튼으로 참여하세요.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="🎁 물품", value=물품, inline=False)
        embed.add_field(name="👤 주최자", value=주최자.mention, inline=True)
        embed.add_field(name="🎟️ 참여", value="1인 1회", inline=True)
        embed.add_field(name="🎲 가중치", value="역할별 무료 이벤트 당첨 가중치 적용", inline=False)
        if 최대참여:
            embed.add_field(name="👥 최대 참여", value=f"{최대참여}명", inline=True)
        embed.set_footer(text=f"이벤트 ID: {event_id}")
        await interaction.channel.send(embed=embed, view=EventView(event_id))
        await interaction.response.send_message("✅ 이벤트 생성 완료.", ephemeral=True)

    @bot.tree.command(name="확률업", description="[관리자] 무료 이벤트에서 특정 역할의 당첨 가중치를 설정합니다.")
    @app_commands.describe(역할="가중치를 올릴 역할", 배율="예: 1.5 = 기본 대비 1.5배")
    @admin_only()
    async def probability_up(interaction: discord.Interaction, 역할: discord.Role, 배율: float):
        if not 1.0 <= 배율 <= 100.0:
            return await interaction.response.send_message("❌ 배율은 1.0~100.0 사이로 설정하세요.", ephemeral=True)
        c = get_conn()
        c.execute(
            "INSERT INTO best_role_weights VALUES(?,?,?) ON CONFLICT(guild_id,role_id) DO UPDATE SET multiplier=excluded.multiplier",
            (interaction.guild_id, 역할.id, 배율),
        )
        c.commit()
        c.close()
        await interaction.response.send_message(
            f"✅ {역할.mention}의 무료 이벤트 당첨 가중치를 **{배율:.2f}배**로 설정했습니다.",
            ephemeral=True,
        )

    @bot.tree.command(name="루에드알림", description="루에드 유튜브 새 영상 알림을 켜거나 끕니다.")
    @app_commands.describe(켜기="True면 구독, False면 취소")
    async def roued_alert(interaction: discord.Interaction, 켜기: bool = True):
        ref = ROUED_CHANNEL.strip()
        c = get_conn()
        if 켜기:
            c.execute(
                "INSERT OR IGNORE INTO best_yt_subs(guild_id,user_id,channel_ref) VALUES(?,?,?)",
                (interaction.guild_id, interaction.user.id, ref),
            )
            msg = "🔔 루에드 유튜브 알림을 켰습니다."
        else:
            c.execute(
                "DELETE FROM best_yt_subs WHERE guild_id=? AND user_id=? AND channel_ref=?",
                (interaction.guild_id, interaction.user.id, ref),
            )
            msg = "🔕 루에드 유튜브 알림을 껐습니다."
        c.commit()
        c.close()
        await interaction.response.send_message(msg, ephemeral=True)

    @bot.tree.command(name="루에드채널설정", description="[관리자] 루에드 유튜브 채널 주소를 저장합니다.")
    @app_commands.describe(채널="루에드 유튜브 채널 URL 또는 채널 ID")
    @admin_only()
    async def roued_channel(interaction: discord.Interaction, 채널: str):
        c = get_conn()
        c.execute(
            "INSERT INTO best_yt_settings(guild_id,notify_channel_id,enabled) VALUES(?,?,1) ON CONFLICT(guild_id) DO UPDATE SET notify_channel_id=excluded.notify_channel_id,enabled=1",
            (interaction.guild_id, interaction.channel_id),
        )
        c.execute("DELETE FROM best_yt_subs WHERE guild_id=? AND channel_ref=?", (interaction.guild_id, ROUED_CHANNEL))
        c.execute(
            "INSERT OR IGNORE INTO best_yt_subs(guild_id,user_id,channel_ref) VALUES(?,?,?)",
            (interaction.guild_id, interaction.user.id, 채널.strip()),
        )
        c.commit()
        c.close()
        await interaction.response.send_message(
            f"✅ 루에드 유튜브 채널을 `{채널.strip()}`로 저장했습니다. 알림 채널은 {interaction.channel.mention}입니다.",
            ephemeral=True,
        )

    async def branding_ready():
        await bot.wait_until_ready()
        try:
            await bot.change_presence(activity=discord.Game(name=BOT_NAME))
        except Exception:
            pass
        for guild in bot.guilds:
            try:
                me = guild.me or guild.get_member(bot.user.id)
                if me and me.guild_permissions.manage_nicknames:
                    await me.edit(nick=BOT_NAME)
            except Exception:
                pass

    bot.add_listener(branding_ready, "on_ready")
    bot.add_view(EventView(0))
    print(f"[BEST] branding loaded: {BOT_NAME}")
