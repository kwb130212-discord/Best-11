# -*- coding: utf-8 -*-
"""BEST-11 v2 운영/관리 업그레이드."""
import time
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands

KST = timezone(timedelta(hours=9))


def setup_upgrade(bot, get_conn, admin_only):
    def now():
        return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    c = get_conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS best_chat_stats (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        user_name TEXT NOT NULL,
        message_count INTEGER NOT NULL DEFAULT 0,
        last_message_at TEXT,
        PRIMARY KEY (guild_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS best_warnings (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        user_name TEXT NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS best_moderation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        moderator_id INTEGER NOT NULL,
        target_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL
    );
    """)
    c.commit()
    c.close()

    async def reply(i, text, *, ephemeral=True):
        if i.response.is_done():
            await i.followup.send(text, ephemeral=ephemeral)
        else:
            await i.response.send_message(text, ephemeral=ephemeral)

    async def log_mod(guild, moderator, target, action, reason):
        c = get_conn()
        c.execute(
            "INSERT INTO best_moderation_logs(guild_id,moderator_id,target_id,action,reason,created_at) VALUES(?,?,?,?,?,?)",
            (guild.id, moderator.id, target.id, action, reason or "", now()),
        )
        c.commit()
        c.close()

    @bot.tree.command(name="명령어", description="현재 등록된 BEST 봇 명령어를 카테고리별로 보여줍니다.")
    async def command_list(i: discord.Interaction):
        commands = sorted(bot.tree.get_commands(), key=lambda x: x.name)
        names = [f"`/{c.name}` — {c.description or '설명 없음'}" for c in commands]
        text = "\n".join(names) or "등록된 명령어가 없습니다."
        if len(text) > 3900:
            text = text[:3890] + "\n…"
        e = discord.Embed(title="📚 BEST 명령어", description=text, color=discord.Color.blurple())
        e.set_footer(text=f"총 {len(commands)}개")
        await i.response.send_message(embed=e, ephemeral=True)

    @bot.tree.command(name="봇상태", description="봇 연결 상태와 서버/명령어 정보를 확인합니다.")
    async def bot_status(i: discord.Interaction):
        latency = round(bot.latency * 1000)
        e = discord.Embed(title="🤖 BEST 봇 상태", color=discord.Color.green())
        e.add_field(name="상태", value="🟢 정상", inline=True)
        e.add_field(name="핑", value=f"{latency}ms", inline=True)
        e.add_field(name="서버", value=f"{len(bot.guilds)}개", inline=True)
        e.add_field(name="명령어", value=f"{len(bot.tree.get_commands())}개", inline=True)
        e.add_field(name="Discord.py", value=discord.__version__, inline=True)
        await i.response.send_message(embed=e, ephemeral=True)

    @bot.tree.command(name="서버정보", description="현재 서버의 기본 정보를 보여줍니다.")
    async def server_info(i: discord.Interaction):
        g = i.guild
        e = discord.Embed(title=f"🏠 {g.name}", color=discord.Color.blurple())
        e.add_field(name="서버 ID", value=str(g.id), inline=True)
        e.add_field(name="멤버", value=str(g.member_count or 0), inline=True)
        e.add_field(name="채널", value=str(len(g.channels)), inline=True)
        e.add_field(name="역할", value=str(len(g.roles)), inline=True)
        e.add_field(name="생성일", value=g.created_at.astimezone(KST).strftime("%Y-%m-%d %H:%M"), inline=True)
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        await i.response.send_message(embed=e)

    @bot.tree.command(name="채팅순위", description="서버 내 누적 채팅량 순위를 보여줍니다.")
    @app_commands.describe(개수="표시할 인원 수 (1~20)")
    async def chat_rank(i: discord.Interaction, 개수: app_commands.Range[int, 1, 20] = 10):
        c = get_conn()
        rows = c.execute(
            "SELECT user_id,user_name,message_count FROM best_chat_stats WHERE guild_id=? ORDER BY message_count DESC, user_id ASC LIMIT ?",
            (i.guild_id, 개수),
        ).fetchall()
        c.close()
        if not rows:
            return await reply(i, "📊 아직 집계된 채팅 데이터가 없습니다.")
        lines = []
        for n, row in enumerate(rows, 1):
            member = i.guild.get_member(row["user_id"])
            name = member.display_name if member else row["user_name"]
            lines.append(f"**{n}.** {name} — `{row['message_count']:,}회`")
        e = discord.Embed(title="💬 채팅 순위", description="\n".join(lines), color=discord.Color.gold())
        await i.response.send_message(embed=e)

    @bot.tree.command(name="경고", description="[관리자] 서버 규칙 위반 경고를 1회 추가합니다.")
    @app_commands.describe(대상="경고 대상", 사유="경고 사유")
    @admin_only()
    async def warn(i: discord.Interaction, 대상: discord.Member, 사유: str = "사유 없음"):
        if 대상.bot:
            return await reply(i, "❌ 봇 계정에는 경고를 부여할 수 없습니다.")
        if 대상 == i.user:
            return await reply(i, "❌ 자신에게 경고를 부여할 수 없습니다.")
        if 대상.top_role >= i.user.top_role and i.user.id != i.guild.owner_id:
            return await reply(i, "❌ 자신과 같거나 높은 역할의 멤버는 처리할 수 없습니다.")
        c = get_conn()
        c.execute(
            "INSERT INTO best_warnings(guild_id,user_id,user_name,count,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(guild_id,user_id) DO UPDATE SET user_name=excluded.user_name,count=count+1,updated_at=excluded.updated_at",
            (i.guild_id, 대상.id, 대상.display_name, 1, now()),
        )
        row = c.execute("SELECT count FROM best_warnings WHERE guild_id=? AND user_id=?", (i.guild_id, 대상.id)).fetchone()
        c.commit()
        c.close()
        await log_mod(i.guild, i.user, 대상, "WARN", 사유)
        await i.response.send_message(f"⚠️ {대상.mention} 경고가 추가되었습니다. 현재 **{row['count']}회**\n사유: {사유}")

    @bot.tree.command(name="경고조회", description="멤버의 누적 경고를 확인합니다.")
    @app_commands.describe(대상="조회할 멤버")
    async def warn_check(i: discord.Interaction, 대상: discord.Member):
        c = get_conn()
        row = c.execute("SELECT count,updated_at FROM best_warnings WHERE guild_id=? AND user_id=?", (i.guild_id, 대상.id)).fetchone()
        c.close()
        count = row["count"] if row else 0
        updated = row["updated_at"] if row else "기록 없음"
        await i.response.send_message(f"⚠️ {대상.mention} 경고: **{count}회**\n최근 변경: `{updated}`", ephemeral=True)

    @bot.tree.command(name="경고초기화", description="[관리자] 멤버의 누적 경고를 초기화합니다.")
    @app_commands.describe(대상="초기화할 멤버", 사유="초기화 사유")
    @admin_only()
    async def warn_clear(i: discord.Interaction, 대상: discord.Member, 사유: str = "사유 없음"):
        c = get_conn()
        c.execute("DELETE FROM best_warnings WHERE guild_id=? AND user_id=?", (i.guild_id, 대상.id))
        c.commit()
        c.close()
        await log_mod(i.guild, i.user, 대상, "WARN_CLEAR", 사유)
        await i.response.send_message(f"✅ {대상.mention}의 경고 기록을 초기화했습니다.\n사유: {사유}", ephemeral=True)

    @bot.tree.command(name="킥", description="[관리자] 멤버를 서버에서 추방합니다.")
    @app_commands.describe(대상="추방할 멤버", 사유="추방 사유")
    @admin_only()
    async def kick(i: discord.Interaction, 대상: discord.Member, 사유: str = "사유 없음"):
        if 대상.bot:
            return await reply(i, "❌ 봇 계정은 이 명령어로 처리하지 않습니다.")
        if 대상 == i.user:
            return await reply(i, "❌ 자신을 추방할 수 없습니다.")
        if 대상 == i.guild.owner:
            return await reply(i, "❌ 서버 소유자는 추방할 수 없습니다.")
        if i.user.id != i.guild.owner_id and 대상.top_role >= i.user.top_role:
            return await reply(i, "❌ 자신과 같거나 높은 역할의 멤버는 추방할 수 없습니다.")
        if not i.guild.me.guild_permissions.kick_members:
            return await reply(i, "❌ 봇에게 멤버 추방 권한이 없습니다.")
        try:
            await 대상.kick(reason=f"{i.user} | {사유}")
        except discord.Forbidden:
            return await reply(i, "❌ Discord 권한 또는 역할 계층 때문에 추방할 수 없습니다.")
        except discord.HTTPException as exc:
            return await reply(i, f"❌ 추방 요청이 실패했습니다: {exc}")
        await log_mod(i.guild, i.user, 대상, "KICK", 사유)
        await i.response.send_message(f"👢 {대상}을(를) 서버에서 추방했습니다.\n사유: {사유}")

    async def track_message(message: discord.Message):
        if not message.guild or message.author.bot:
            return
        content = (message.content or "").strip()
        if not content and not message.attachments:
            return
        c = get_conn()
        c.execute(
            "INSERT INTO best_chat_stats(guild_id,user_id,user_name,message_count,last_message_at) VALUES(?,?,?,?,?) ON CONFLICT(guild_id,user_id) DO UPDATE SET user_name=excluded.user_name,message_count=message_count+1,last_message_at=excluded.last_message_at",
            (message.guild.id, message.author.id, message.author.display_name, 1, now()),
        )
        c.commit()
        c.close()

    bot.add_listener(track_message, "on_message")
    print("[BEST] v2 upgrade loaded: commands/chat ranking/warnings/kick")
