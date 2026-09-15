# -*- coding: utf-8 -*-
"""BEST 클랜 승률/등급 관리 시스템."""
import discord
from discord import app_commands

RANKS = (
    ("정예", 70.0, "🏆"),
    ("1군", 55.0, "🥇"),
    ("2군", 40.0, "🥈"),
    ("3군", 0.0, "🥉"),
)


def setup_clan_rank(bot, get_conn, admin_only):
    def init_db():
        c = get_conn()
        c.execute('''CREATE TABLE IF NOT EXISTS clan_records (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(guild_id, user_id)
        )''')
        c.commit()
        c.close()

    init_db()

    def rank_for(wins, losses):
        games = wins + losses
        if games <= 0:
            return "3군", 0.0, "🥉"
        rate = wins / games * 100.0
        for name, minimum, icon in RANKS:
            if rate >= minimum:
                return name, rate, icon
        return "3군", rate, "🥉"

    async def ensure_rank_roles(guild):
        roles = {}
        for name, _, _ in RANKS:
            role = discord.utils.get(guild.roles, name=name)
            if role is None:
                try:
                    role = await guild.create_role(name=name, reason="BEST 승률 등급 자동 생성")
                except (discord.Forbidden, discord.HTTPException):
                    continue
            roles[name] = role
        return roles

    async def refresh_member_rank(guild, user_id):
        member = guild.get_member(user_id)
        if member is None or member.bot:
            return None
        c = get_conn()
        row = c.execute('SELECT wins, losses FROM clan_records WHERE guild_id=? AND user_id=?', (guild.id, user_id)).fetchone()
        c.close()
        wins = int(row['wins']) if row else 0
        losses = int(row['losses']) if row else 0
        rank, rate, icon = rank_for(wins, losses)
        roles = await ensure_rank_roles(guild)
        rank_role = roles.get(rank)
        if rank_role is not None:
            remove = [r for r in member.roles if r.name in {x[0] for x in RANKS} and r.id != rank_role.id]
            try:
                if remove:
                    await member.remove_roles(*remove, reason="승률 등급 자동 갱신")
                if rank_role not in member.roles:
                    await member.add_roles(rank_role, reason="승률 등급 자동 갱신")
            except (discord.Forbidden, discord.HTTPException):
                pass
        return rank, rate, wins, losses

    @bot.tree.command(name='전적', description='내 클랜 승률과 등급을 확인합니다.')
    @app_commands.describe(대상='확인할 클랜원 (선택)')
    async def record(i: discord.Interaction, 대상: discord.Member = None):
        member = 대상 or i.user
        c = get_conn()
        row = c.execute('SELECT wins, losses FROM clan_records WHERE guild_id=? AND user_id=?', (i.guild_id, member.id)).fetchone()
        c.close()
        wins = int(row['wins']) if row else 0
        losses = int(row['losses']) if row else 0
        rank, rate, _, _ = rank_for(wins, losses)
        games = wins + losses
        e = discord.Embed(title=f'📊 {member.display_name} 전적', color=discord.Color.blurple())
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name='🏆 등급', value=f'**{rank}**', inline=True)
        e.add_field(name='📈 승률', value=f'**{rate:.1f}%**', inline=True)
        e.add_field(name='⚔️ 경기', value=f'**{games}경기**', inline=True)
        e.add_field(name='🟢 승', value=f'{wins}승', inline=True)
        e.add_field(name='🔴 패', value=f'{losses}패', inline=True)
        if games < 5:
            e.set_footer(text=f'등급은 현재 승률 기준이며, {5-games}경기 더 쌓이면 표본이 안정됩니다.')
        await i.response.send_message(embed=e)

    @bot.tree.command(name='전적기록', description='[관리자] 클랜원의 승/패 전적을 기록하고 등급을 갱신합니다.')
    @app_commands.describe(대상='대상 클랜원', 결과='승 또는 패', 경기수='기록할 경기 수')
    @admin_only()
    async def record_result(i: discord.Interaction, 대상: discord.Member, 결과: str, 경기수: app_commands.Range[int, 1, 20] = 1):
        if 대상.bot:
            return await i.response.send_message('❌ 봇의 전적은 기록할 수 없습니다.', ephemeral=True)
        result = 결과.strip().lower()
        if result not in {'승', '패', 'win', 'loss', 'w', 'l'}:
            return await i.response.send_message('❌ 결과는 `승` 또는 `패`로 입력해주세요.', ephemeral=True)
        c = get_conn()
        c.execute('INSERT OR IGNORE INTO clan_records(guild_id,user_id,wins,losses) VALUES(?,?,0,0)', (i.guild_id, 대상.id))
        if result in {'승', 'win', 'w'}:
            c.execute('UPDATE clan_records SET wins=wins+? WHERE guild_id=? AND user_id=?', (경기수, i.guild_id, 대상.id))
        else:
            c.execute('UPDATE clan_records SET losses=losses+? WHERE guild_id=? AND user_id=?', (경기수, i.guild_id, 대상.id))
        c.commit()
        c.close()
        data = await refresh_member_rank(i.guild, 대상.id)
        rank, rate, wins, losses = data
        await i.response.send_message(
            f'✅ {대상.mention} 전적 반영 완료: **{경기수}경기 {"승" if result in {"승", "win", "w"} else "패"}**\n'
            f'📊 {wins}승 {losses}패 · 승률 **{rate:.1f}%** · 등급 **{rank}**'
        )

    @bot.tree.command(name='전적초기화', description='[관리자] 클랜원의 전적을 초기화합니다.')
    @app_commands.describe(대상='대상 클랜원')
    @admin_only()
    async def record_reset(i: discord.Interaction, 대상: discord.Member):
        c = get_conn()
        c.execute('DELETE FROM clan_records WHERE guild_id=? AND user_id=?', (i.guild_id, 대상.id))
        c.commit()
        c.close()
        await refresh_member_rank(i.guild, 대상.id)
        await i.response.send_message(f'✅ {대상.mention}의 전적을 0승 0패로 초기화했습니다.')

    @bot.tree.command(name='승률순위', description='클랜원 승률 TOP 10을 확인합니다.')
    async def record_rank(i: discord.Interaction):
        c = get_conn()
        rows = c.execute('''SELECT user_id,wins,losses FROM clan_records
                            WHERE guild_id=? AND wins+losses>0
                            ORDER BY CAST(wins AS REAL)/(wins+losses) DESC, wins DESC LIMIT 10''', (i.guild_id,)).fetchall()
        c.close()
        lines = []
        for idx, row in enumerate(rows, 1):
            m = i.guild.get_member(row['user_id'])
            if not m or m.bot:
                continue
            rank, rate, wins, losses = rank_for(int(row['wins']), int(row['losses']))
            lines.append(f'**{idx}.** {m.mention} · **{rank}** · {rate:.1f}% ({wins}승 {losses}패)')
        e = discord.Embed(title='🏆 BEST 승률 TOP 10', description='\n'.join(lines) or '아직 전적이 없습니다.', color=discord.Color.gold())
        await i.response.send_message(embed=e)

    @bot.tree.command(name='등급갱신', description='[관리자] 모든 클랜원의 승률 등급 역할을 갱신합니다.')
    @admin_only()
    async def refresh_all(i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        count = 0
        for member in i.guild.members:
            if member.bot:
                continue
            data = await refresh_member_rank(i.guild, member.id)
            if data:
                count += 1
        await i.followup.send(f'✅ 승률 등급 역할 갱신 완료: **{count}명**', ephemeral=True)
