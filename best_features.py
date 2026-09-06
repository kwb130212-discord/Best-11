# -*- coding: utf-8 -*-
import asyncio, os, random, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands

KST = timezone(timedelta(hours=9))

def setup_best_features(bot, get_conn, admin_only):
    def init_db():
        c=get_conn(); c.executescript('''
        CREATE TABLE IF NOT EXISTS best_events(id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER,channel_id INTEGER,title TEXT,description TEXT,max_entries INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT);
        CREATE TABLE IF NOT EXISTS best_event_entries(event_id INTEGER,user_id INTEGER,user_name TEXT,created_at TEXT,PRIMARY KEY(event_id,user_id));
        CREATE TABLE IF NOT EXISTS best_role_weights(guild_id INTEGER,role_id INTEGER,multiplier REAL DEFAULT 1.0,PRIMARY KEY(guild_id,role_id));
        CREATE TABLE IF NOT EXISTS best_yt_subs(guild_id INTEGER,user_id INTEGER,channel_ref TEXT,channel_id TEXT,last_video_id TEXT,PRIMARY KEY(guild_id,user_id,channel_ref));
        CREATE TABLE IF NOT EXISTS best_yt_settings(guild_id INTEGER PRIMARY KEY,notify_channel_id INTEGER,enabled INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS best_recurring(id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER,channel_id INTEGER,title TEXT,weekday INTEGER,hour INTEGER,minute INTEGER,description TEXT,last_key TEXT,active INTEGER DEFAULT 1);
        '''); c.commit(); c.close()
    init_db()
    def now(): return datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    def weight(gid,m):
        c=get_conn(); rows=c.execute('SELECT role_id,multiplier FROM best_role_weights WHERE guild_id=?',(gid,)).fetchall(); c.close()
        return max([float(r['multiplier']) for r in rows if any(x.id==r['role_id'] for x in m.roles)]+[1.0])
    async def eph(i,msg):
        if i.response.is_done(): await i.followup.send(msg,ephemeral=True)
        else: await i.response.send_message(msg,ephemeral=True)

    class EventView(discord.ui.View):
        def __init__(self,eid): super().__init__(timeout=None); self.eid=eid
        @discord.ui.button(label='🎟️ 이벤트 참여',style=discord.ButtonStyle.success,custom_id='best_event_join')
        async def join(self,i,b):
            c=get_conn(); e=c.execute('SELECT * FROM best_events WHERE id=? AND guild_id=? AND active=1',(self.eid,i.guild_id)).fetchone(); n=c.execute('SELECT COUNT(*) c FROM best_event_entries WHERE event_id=?',(self.eid,)).fetchone()['c']
            if not e: c.close(); return await eph(i,'❌ 종료되었거나 존재하지 않는 이벤트입니다.')
            if c.execute('SELECT 1 FROM best_event_entries WHERE event_id=? AND user_id=?',(self.eid,i.user.id)).fetchone(): c.close(); return await eph(i,'⚠️ 이미 참여했습니다.')
            if e['max_entries'] and n>=e['max_entries']: c.close(); return await eph(i,'❌ 참여 인원이 가득 찼습니다.')
            c.execute('INSERT INTO best_event_entries VALUES(?,?,?,?)',(self.eid,i.user.id,i.user.display_name,now())); c.commit(); c.close(); await eph(i,'✅ 이벤트 참여 완료!')
        @discord.ui.button(label='🎲 내 가중치',style=discord.ButtonStyle.primary,custom_id='best_event_odds')
        async def odds(self,i,b): await eph(i,f'🎲 현재 이벤트 추첨 가중치: **{weight(i.guild_id,i.user):.2f}배**')

    class ScrimApplyView(discord.ui.View):
        def __init__(self,sid): super().__init__(timeout=None); self.sid=sid
        @discord.ui.button(label='🟢 내전 참여 신청',style=discord.ButtonStyle.success,custom_id='best_scrim_apply')
        async def apply(self,i,b):
            c=get_conn(); c.execute("INSERT OR REPLACE INTO scrim_participants(scrim_id,user_id,user_name,status) VALUES(?,?,?,?)",(self.sid,i.user.id,i.user.display_name,'attend')); c.commit(); c.close(); await eph(i,'✅ 내전 참여 신청 완료!')
        @discord.ui.button(label='❌ 신청 취소',style=discord.ButtonStyle.danger,custom_id='best_scrim_cancel')
        async def cancel(self,i,b):
            c=get_conn(); c.execute('DELETE FROM scrim_participants WHERE scrim_id=? AND user_id=?',(self.sid,i.user.id)); c.commit(); c.close(); await eph(i,'✅ 신청을 취소했습니다.')
        @discord.ui.button(label='👥 신청자 보기',style=discord.ButtonStyle.secondary,custom_id='best_scrim_list')
        async def listing(self,i,b):
            c=get_conn(); rows=c.execute("SELECT user_name FROM scrim_participants WHERE scrim_id=? AND status='attend'",(self.sid,)).fetchall(); c.close(); text='\n'.join('• '+r['user_name'] for r in rows) or '아직 신청자가 없습니다.'; await i.response.send_message(embed=discord.Embed(title='👥 내전 신청자',description=text[:3900]),ephemeral=True)

    @bot.tree.command(name='이벤트생성',description='[관리자] BEST 이벤트 패널 생성')
    @app_commands.describe(제목='이벤트 제목',설명='설명',최대참여='0=제한없음')
    @admin_only()
    async def event_create(i,제목:str,설명:str='',최대참여:int=0):
        c=get_conn(); cur=c.cursor(); cur.execute('INSERT INTO best_events(guild_id,channel_id,title,description,max_entries,created_at) VALUES(?,?,?,?,?,?)',(i.guild_id,i.channel_id,제목,설명,max(0,최대참여),now())); eid=cur.lastrowid; c.commit(); c.close()
        e=discord.Embed(title='🎉 BEST 이벤트 | '+제목,description=설명 or '아래 버튼으로 참여하세요.',color=discord.Color.gold()); e.add_field(name='🎟️ 참여',value='1인 1회'); e.add_field(name='🎲 추첨',value='역할별 가중치'); e.set_footer(text=f'이벤트 ID: {eid}'); await i.channel.send(embed=e,view=EventView(eid)); await i.response.send_message('✅ 이벤트 패널 생성 완료.',ephemeral=True)

    @bot.tree.command(name='이벤트추첨',description='[관리자] 이벤트 가중치 추첨')
    @app_commands.describe(이벤트ID='이벤트 ID')
    @admin_only()
    async def event_draw(i,이벤트ID:int):
        c=get_conn(); e=c.execute('SELECT * FROM best_events WHERE id=? AND guild_id=?',(이벤트ID,i.guild_id)).fetchone(); rows=c.execute('SELECT user_id FROM best_event_entries WHERE event_id=?',(이벤트ID,)).fetchall(); c.close()
        if not e or not rows: return await i.response.send_message('❌ 이벤트 또는 참여자가 없습니다.',ephemeral=True)
        ms=[i.guild.get_member(r['user_id']) for r in rows]; ms=[m for m in ms if m]; winner=random.choices(ms,weights=[weight(i.guild_id,m) for m in ms],k=1)[0]
        c=get_conn(); c.execute('UPDATE best_events SET active=0 WHERE id=?',(이벤트ID,)); c.commit(); c.close(); await i.response.send_message(embed=discord.Embed(title='🎊 BEST 이벤트 당첨!',description=f'🏆 {winner.mention}\n🎲 가중치 {weight(i.guild_id,winner):.2f}배',color=discord.Color.green()))

    @bot.tree.command(name='추첨역할설정',description='[관리자] 역할별 추첨 가중치 설정')
    @app_commands.describe(역할='역할',배율='예: 1.5')
    @admin_only()
    async def role_weight(i,역할:discord.Role,배율:float):
        if not 0<배율<=100: return await i.response.send_message('❌ 배율은 0 초과 100 이하입니다.',ephemeral=True)
        c=get_conn(); c.execute('INSERT INTO best_role_weights VALUES(?,?,?) ON CONFLICT(guild_id,role_id) DO UPDATE SET multiplier=excluded.multiplier',(i.guild_id,역할.id,배율)); c.commit(); c.close(); await i.response.send_message(f'✅ {역할.mention} = **{배율:.2f}배**',ephemeral=True)

    @bot.tree.command(name='내전패널',description='[관리자] 기존 스크림을 참여 신청형 임베드로 표시')
    @app_commands.describe(스크림ID='스크림 ID')
    @admin_only()
    async def scrim_panel(i,스크림ID:int):
        c=get_conn(); r=c.execute('SELECT * FROM scrim_schedules WHERE id=? AND guild_id=?',(스크림ID,i.guild_id)).fetchone(); c.close()
        if not r: return await i.response.send_message('❌ 스크림을 찾을 수 없습니다.',ephemeral=True)
        e=discord.Embed(title='⚔️ BEST 내전 | '+r['title'],description=f"📅 {r['scrim_time']}\n📝 {r['description'] or '설명 없음'}\n\n아래 버튼으로 신청하세요.",color=discord.Color.blurple()); await i.channel.send(embed=e,view=ScrimApplyView(스크림ID)); await i.response.send_message('✅ 내전 패널 생성 완료.',ephemeral=True)

    @bot.tree.command(name='정기내전등록',description='[관리자] 매주 반복 내전 자동 등록')
    @app_commands.describe(제목='제목',요일='월=0~일=6',시='0~23',분='0~59',설명='내용')
    @admin_only()
    async def recurring(i,제목:str,요일:int,시:int,분:int,설명:str=''):
        if not 0<=요일<=6 or not 0<=시<=23 or not 0<=분<=59: return await i.response.send_message('❌ 요일 0~6, 시 0~23, 분 0~59',ephemeral=True)
        c=get_conn(); c.execute('INSERT INTO best_recurring(guild_id,channel_id,title,weekday,hour,minute,description) VALUES(?,?,?,?,?,?,?)',(i.guild_id,i.channel_id,제목,요일,시,분,설명)); c.commit(); c.close(); await i.response.send_message('✅ 매주 자동 게시되는 정기내전을 등록했습니다.',ephemeral=True)

    @bot.tree.command(name='유튜브알림설정',description='[관리자] YouTube 알림 채널 설정')
    @app_commands.describe(채널='알림을 보낼 채널')
    @admin_only()
    async def yt_channel(i,채널:discord.TextChannel):
        c=get_conn(); c.execute('INSERT INTO best_yt_settings VALUES(?,?,1) ON CONFLICT(guild_id) DO UPDATE SET notify_channel_id=excluded.notify_channel_id,enabled=1',(i.guild_id,채널.id)); c.commit(); c.close(); await i.response.send_message(f'✅ YouTube 알림 채널: {채널.mention}',ephemeral=True)

    @bot.tree.command(name='유튜브구독',description='유튜버 새 영상 알림을 구독')
    @app_commands.describe(채널='YouTube 채널 URL 또는 채널 ID')
    async def yt_sub(i,채널:str):
        ref=채널.strip(); c=get_conn(); c.execute('INSERT OR IGNORE INTO best_yt_subs(guild_id,user_id,channel_ref) VALUES(?,?,?)',(i.guild_id,i.user.id,ref)); c.commit(); c.close(); await i.response.send_message(f'🔔 {ref} 알림 구독 완료. 새 영상이 올라오면 구독자만 멘션합니다.',ephemeral=True)

    @bot.tree.command(name='유튜브구독취소',description='YouTube 알림 구독 취소')
    @app_commands.describe(채널='같은 채널 URL 또는 ID')
    async def yt_unsub(i,채널:str):
        c=get_conn(); c.execute('DELETE FROM best_yt_subs WHERE guild_id=? AND user_id=? AND channel_ref=?',(i.guild_id,i.user.id,채널.strip())); c.commit(); c.close(); await i.response.send_message('🔕 구독 취소 완료.',ephemeral=True)

    async def channel_id(ref):
        if ref.startswith('UC'): return ref
        if 'channel/' in ref: return ref.split('channel/',1)[1].split('/',1)[0].split('?',1)[0]
        url=ref if ref.startswith('http') else 'https://www.youtube.com/'+ref.lstrip('@')
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}); html=await asyncio.to_thread(lambda:urllib.request.urlopen(req,timeout=8).read().decode('utf-8','ignore')); marker='"channelId":"'; p=html.find(marker); return html[p+len(marker):].split('"',1)[0] if p>=0 else None
        except Exception: return None
    async def latest(cid):
        if not cid:return None
        try:
            u='https://www.youtube.com/feeds/videos.xml?channel_id='+urllib.parse.quote(cid); req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}); data=await asyncio.to_thread(lambda:urllib.request.urlopen(req,timeout=10).read()); root=ET.fromstring(data); ns={'a':'http://www.w3.org/2005/Atom','yt':'http://www.youtube.com/xml/schemas/2015'}; x=root.find('a:entry',ns); vid=x.findtext('yt:videoId',namespaces=ns) if x is not None else None; title=x.findtext('a:title',namespaces=ns) if x is not None else None; return {'id':vid,'title':title or '새 영상','url':'https://www.youtube.com/watch?v='+vid} if vid else None
        except Exception:return None
    async def yt_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            try:
                c=get_conn(); rows=c.execute('SELECT * FROM best_yt_subs').fetchall(); c.close(); groups={}
                for r in rows: groups.setdefault((r['guild_id'],r['channel_ref']),[]).append(r)
                for (gid,ref),subs in groups.items():
                    cid=subs[0]['channel_id']
                    if not cid:
                        cid=await channel_id(ref)
                        if cid:
                            c=get_conn(); c.execute('UPDATE best_yt_subs SET channel_id=? WHERE guild_id=? AND channel_ref=?',(cid,gid,ref)); c.commit(); c.close()
                    v=await latest(cid)
                    if not v: continue
                    old=subs[0]['last_video_id']
                    c=get_conn()
                    if not old: c.execute('UPDATE best_yt_subs SET last_video_id=? WHERE guild_id=? AND channel_ref=?',(v['id'],gid,ref)); c.commit(); c.close(); continue
                    if old==v['id']: c.close(); continue
                    s=c.execute('SELECT * FROM best_yt_settings WHERE guild_id=? AND enabled=1',(gid,)).fetchone(); c.close(); g=bot.get_guild(gid)
                    if s and g:
                        ch=g.get_channel(s['notify_channel_id'])
                        if ch:
                            mentions=' '.join(f"<@{r['user_id']}>" for r in subs); e=discord.Embed(title='📺 BEST YouTube 새 영상',description=f"**{v['title']}**\n{v['url']}",color=discord.Color.red()); await ch.send(content=mentions,embed=e,allowed_mentions=discord.AllowedMentions(users=True))
                    c=get_conn(); c.execute('UPDATE best_yt_subs SET last_video_id=? WHERE guild_id=? AND channel_ref=?',(v['id'],gid,ref)); c.commit(); c.close()
            except Exception as ex: print('[BEST-YOUTUBE]',ex)
            await asyncio.sleep(max(30,int(os.getenv('YOUTUBE_POLL_SECONDS','120'))))
    async def recurring_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            try:
                n=datetime.now(KST); key=n.strftime('%Y-%m-%d-%H-%M'); c=get_conn(); rows=c.execute('SELECT * FROM best_recurring WHERE active=1 AND weekday=? AND hour=? AND minute=?',(n.weekday(),n.hour,n.minute)).fetchall()
                for r in rows:
                    if r['last_key']==key:continue
                    ch=bot.get_channel(r['channel_id'])
                    if ch:
                        cur=c.cursor(); cur.execute('INSERT INTO scrim_schedules(guild_id,title,scrim_time,description,author_id,created_at) VALUES(?,?,?,?,?,?)',(r['guild_id'],r['title'],n.strftime('%Y-%m-%d %H:%M'),r['description'],bot.user.id,now())); sid=cur.lastrowid; e=discord.Embed(title='⚔️ 정기내전 | '+r['title'],description=f"📅 {n.strftime('%Y-%m-%d %H:%M')}\n📝 {r['description'] or '설명 없음'}\n\n아래 버튼으로 참여 신청하세요.",color=discord.Color.blurple()); await ch.send(embed=e,view=ScrimApplyView(sid)); c.execute('UPDATE best_recurring SET last_key=? WHERE id=?',(key,r['id']))
                c.commit(); c.close()
            except Exception as ex: print('[BEST-RECURRING]',ex)
            await asyncio.sleep(20)
    async def ready():
        init_db()
        if not getattr(bot,'_best_yt_task',None) or bot._best_yt_task.done(): bot._best_yt_task=asyncio.create_task(yt_loop())
        if not getattr(bot,'_best_recurring_task',None) or bot._best_recurring_task.done(): bot._best_recurring_task=asyncio.create_task(recurring_loop())
    bot.add_listener(ready,'on_ready')
    print('[BEST] clan features loaded')
