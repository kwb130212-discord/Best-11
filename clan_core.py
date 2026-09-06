# -*- coding: utf-8 -*-
"""BEST 클랜 공통 운영 기능."""
import discord
from discord import app_commands
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def setup_clan_core(bot, get_conn, admin_only):
    def now():
        return datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

    def init_db():
        c = get_conn()
        c.executescript('''
        CREATE TABLE IF NOT EXISTS clan_attendance (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            PRIMARY KEY(guild_id, user_id, day)
        );
        CREATE TABLE IF NOT EXISTS clan_warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clan_settings (
            guild_id INTEGER PRIMARY KEY,
            notice_channel_id INTEGER,
            attendance_channel_id INTEGER
        );
        ''')
        c.commit()
        c.close()

    init_db()

    @bot.tree.command(name='클랜정보', description='BEST 클랜의 기본 정보를 확인합니다.')
    async def clan_info(i: discord.Interaction):
        g = i.guild
        if g is None:
            return await i.response.send_message('❌ 서버에서만 사용할 수 있습니다.', ephemeral=True)
        members = [m for m in g.members if not m.bot]
        online = sum(1 for m in members if m.status != discord.Status.offline)
        admins = [m for m in members if m.guild_permissions.administrator]
        e = discord.Embed(title='🏆 BEST 클랜 정보', color=discord.Color.blurple())
        e.add_field(name='👥 클랜원', value=f'{len(members):,}명', inline=True)
        e.add_field(name='🟢 온라인', value=f'{online:,}명', inline=True)
        e.add_field(name='🛡️ 관리자', value=f'{len(admins):,}명', inline=True)
        e.add_field(name='🤖 봇', value=f'{sum(1 for m in g.members if m.bot):,}개', inline=True)
        e.set_footer(text='BEST • 루에드 유튜브')
        await i.response.send_message(embed=e)

    @bot.tree.command(name='내정보', description='내 클랜 활동 정보를 확인합니다.')
    async def my_info(i: discord.Interaction):
        c = get_conn()
        days = c.execute('SELECT COUNT(*) AS n FROM clan_attendance WHERE guild_id=? AND user_id=?', (i.guild_id, i.user.id)).fetchone()['n']
        warns = c.execute('SELECT COUNT(*) AS n FROM clan_warnings WHERE guild_id=? AND user_id=?', (i.guild_id, i.user.id)).fetchone()['n']
        scrims = c.execute("SELECT COUNT(*) AS n FROM scrim_participants WHERE user_id=? AND status='attend'", (i.user.id,)).fetchone()['n']
        joins = c.execute('SELECT join_count FROM user_join_counts WHERE guild_id=? AND user_id=?', (i.guild_id, i.user.id)).fetchone()
        c.close()
        e = discord.Embed(title=f'👤 {i.user.display_name}님의 클랜 정보', color=discord.Color.blurple())
        e.set_thumbnail(url=i.user.display_avatar.url)
        e.add_field(name='📅 출석', value=f'{days}일', inline=True)
        e.add_field(name='⚠️ 경고', value=f'{warns}회', inline=True)
        e.add_field(name='⚔️ 스크림 참석', value=f'{scrims}회', inline=True)
        e.add_field(name='🔄 서버 입장', value=f'{joins["join_count"] if joins else 0}회', inline=True)
        await i.response.send_message(embed=e, ephemeral=True)

    @bot.tree.command(name='출석', description='오늘 클랜 출석을 기록합니다.')
    async def attendance(i: discord.Interaction):
        day = datetime.now(KST).strftime('%Y-%m-%d')
        c = get_conn()
        exists = c.execute('SELECT 1 FROM clan_attendance WHERE guild_id=? AND user_id=? AND day=?', (i.guild_id, i.user.id, day)).fetchone()
        if exists:
            c.close()
            return await i.response.send_message('⚠️ 오늘은 이미 출석했습니다.', ephemeral=True)
        c.execute('INSERT INTO clan_attendance VALUES(?,?,?)', (i.guild_id, i.user.id, day))
        total = c.execute('SELECT COUNT(*) AS n FROM clan_attendance WHERE guild_id=? AND user_id=?', (i.guild_id, i.user.id)).fetchone()['n']
        c.commit()
        c.close()
        await i.response.send_message(f'✅ **출석 완료!** 오늘 날짜: `{day}`\n누적 출석: **{total}일**')

    @bot.tree.command(name='출석현황', description='최근 클랜 출석 순위를 확인합니다.')
    async def attendance_rank(i: discord.Interaction):
        c = get_conn()
        rows = c.execute('''SELECT user_id, COUNT(*) AS n FROM clan_attendance
                            WHERE guild_id=? GROUP BY user_id ORDER BY n DESC LIMIT 10''', (i.guild_id,)).fetchall()
        c.close()
        lines = []
        for idx, row in enumerate(rows, 1):
            m = i.guild.get_member(row['user_id'])
            if m:
                lines.append(f'**{idx}.** {m.mention} — `{row["n"]}일`')
        e = discord.Embed(title='📊 클랜 출석 TOP 10', description='\n'.join(lines) or '아직 출석 기록이 없습니다.', color=discord.Color.green())
        await i.response.send_message(embed=e)

    @bot.tree.command(name='공지', description='[관리자] 클랜 공지를 전송합니다.')
    @app_commands.describe(내용='공지 내용', 제목='공지 제목')
    @admin_only()
    async def notice(i: discord.Interaction, 내용: str, 제목: str = '📢 BEST 클랜 공지'):
        e = discord.Embed(title=제목, description=내용, color=discord.Color.gold(), timestamp=datetime.now(KST))
        e.set_footer(text=f'공지 담당: {i.user.display_name}')
        await i.channel.send(embed=e)
        await i.response.send_message('✅ 공지를 전송했습니다.', ephemeral=True)

    @bot.tree.command(name='청소', description='[관리자] 채널의 최근 메시지를 정리합니다.')
    @app_commands.describe(개수='삭제할 메시지 수 (1~100)')
    @admin_only()
    async def purge(i: discord.Interaction, 개수: app_commands.Range[int, 1, 100]):
        if not isinstance(i.channel, discord.TextChannel):
            return await i.response.send_message('❌ 텍스트 채널에서만 사용할 수 있습니다.', ephemeral=True)
        await i.response.defer(ephemeral=True)
        deleted = await i.channel.purge(limit=개수)
        await i.followup.send(f'🧹 **{len(deleted)}개** 메시지를 정리했습니다.', ephemeral=True)

    @bot.tree.command(name='경고', description='[관리자] 클랜원에게 경고를 기록합니다.')
    @app_commands.describe(대상='경고 대상', 사유='경고 사유')
    @admin_only()
    async def warn(i: discord.Interaction, 대상: discord.Member, 사유: str):
        if 대상.bot:
            return await i.response.send_message('❌ 봇에게는 경고를 기록할 수 없습니다.', ephemeral=True)
        c = get_conn()
        c.execute('INSERT INTO clan_warnings(guild_id,user_id,moderator_id,reason,created_at) VALUES(?,?,?,?,?)', (i.guild_id, 대상.id, i.user.id, 사유, now()))
        count = c.execute('SELECT COUNT(*) AS n FROM clan_warnings WHERE guild_id=? AND user_id=?', (i.guild_id, 대상.id)).fetchone()['n']
        c.commit()
        c.close()
        await i.response.send_message(f'⚠️ {대상.mention}에게 경고를 기록했습니다. 현재 **{count}회**\n사유: {사유}')

    @bot.tree.command(name='경고조회', description='클랜원의 경고 기록을 확인합니다.')
    @app_commands.describe(대상='확인할 클랜원')
    async def warn_check(i: discord.Interaction, 대상: discord.Member = None):
        대상 = 대상 or i.user
        c = get_conn()
        rows = c.execute('SELECT reason,created_at,moderator_id FROM clan_warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10', (i.guild_id, 대상.id)).fetchall()
        c.close()
        if not rows:
            return await i.response.send_message(f'✅ {대상.mention}의 경고 기록이 없습니다.', ephemeral=True)
        lines = [f'• `{r["created_at"]}` — {r["reason"]}' for r in rows]
        e = discord.Embed(title=f'⚠️ {대상.display_name} 경고 기록', description='\n'.join(lines), color=discord.Color.orange())
        e.set_footer(text=f'최근 {len(rows)}건 표시')
        await i.response.send_message(embed=e, ephemeral=True)

    @bot.tree.command(name='경고삭제', description='[관리자] 클랜원의 가장 최근 경고를 1개 삭제합니다.')
    @app_commands.describe(대상='대상 클랜원')
    @admin_only()
    async def warn_remove(i: discord.Interaction, 대상: discord.Member):
        c = get_conn()
        row = c.execute('SELECT id FROM clan_warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 1', (i.guild_id, 대상.id)).fetchone()
        if not row:
            c.close()
            return await i.response.send_message('❌ 삭제할 경고가 없습니다.', ephemeral=True)
        c.execute('DELETE FROM clan_warnings WHERE id=?', (row['id'],))
        remaining = c.execute('SELECT COUNT(*) AS n FROM clan_warnings WHERE guild_id=? AND user_id=?', (i.guild_id, 대상.id)).fetchone()['n']
        c.commit()
        c.close()
        await i.response.send_message(f'✅ {대상.mention}의 최근 경고 1개를 삭제했습니다. 현재 **{remaining}회**')

    @bot.tree.command(name='경고초기화', description='[관리자] 클랜원의 모든 경고를 초기화합니다.')
    @app_commands.describe(대상='대상 클랜원')
    @admin_only()
    async def warn_reset(i: discord.Interaction, 대상: discord.Member):
        c = get_conn()
        c.execute('DELETE FROM clan_warnings WHERE guild_id=? AND user_id=?', (i.guild_id, 대상.id))
        c.commit()
        c.close()
        await i.response.send_message(f'✅ {대상.mention}의 경고를 모두 초기화했습니다.')

    @bot.tree.command(name='클랜명령어', description='현재 사용 가능한 BEST 클랜 명령어를 확인합니다.')
    async def commands_list(i: discord.Interaction):
        text = (
            '**🏆 BEST 클랜 기본**\n'
            '`/클랜정보` `/내정보` `/출석` `/출석현황` `/클랜명령어`\n\n'
            '**⚔️ 내전**\n'
            '`/스크림등록` `/내전패널` `/팀짜기` `/정기내전등록`\n\n'
            '**🎉 이벤트**\n'
            '`/이벤트생성` `/이벤트추첨` `/추첨역할설정`\n\n'
            '**📺 YouTube**\n'
            '`/유튜브알림패널` `/루에드알림` `/루에드채널설정`\n\n'
            '**🛡️ 관리자**\n'
            '`/공지` `/청소` `/경고` `/경고조회` `/경고삭제` `/경고초기화` `/로그채널설정`'
        )
        await i.response.send_message(embed=discord.Embed(title='📚 BEST 클랜 명령어', description=text, color=discord.Color.blurple()), ephemeral=True)
