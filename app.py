# -*- coding: utf-8 -*-
import os
import sqlite3
import asyncio
import random
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 환경변수 및 기본 설정
# ---------------------------------------------------------------------------
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ROLE_NAME = os.getenv("ADMIN_ROLE_NAME", "! !디노")
DB_PATH = os.getenv("DB_PATH", "team.db")
VERIFY_ROLE_NAME = os.getenv("VERIFY_ROLE_NAME", "인증유저")
KST = timezone(timedelta(hours=9))

intents = discord.Intents.default()
intents.members = True          
intents.message_content = True  

# ---------------------------------------------------------------------------
# 디스코드 커맨드 트리 및 권한 체크
# ---------------------------------------------------------------------------
class GatedCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None:
            await interaction.response.send_message("이 봇은 서버 안에서만 사용할 수 있어요.", ephemeral=True)
            return False
        return True

bot = commands.Bot(command_prefix="!", intents=intents, tree_cls=GatedCommandTree)

# ---------------------------------------------------------------------------
# 데이터베이스 초기화
# ---------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            welcome_channel_id INTEGER,
            log_channel_id INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scrim_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            scrim_time TEXT NOT NULL,
            description TEXT,
            author_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scrim_participants (
            scrim_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (scrim_id, user_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticket_logs (
            channel_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            opened_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_join_counts (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            join_count INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# 헬퍼 함수들
# ---------------------------------------------------------------------------
def now_kst_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

def is_admin(ctx_or_interaction) -> bool:
    if isinstance(ctx_or_interaction, discord.Interaction):
        member = ctx_or_interaction.user
    else:
        member = ctx_or_interaction.author

    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    if any(role.name == ADMIN_ROLE_NAME for role in member.roles):
        return True
    return False

def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_admin(interaction):
            return True
        await interaction.response.send_message("❌ 이 명령어는 관리자만 사용할 수 있어요.", ephemeral=True)
        return False
    return app_commands.check(predicate)

@bot.event
async def on_ready():
    init_db()
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    bot.add_view(VerifyView())

    try:
        synced = await bot.tree.sync()
        print(f"슬래시 명령어 {len(synced)}개 동기화 완료")
    except Exception as e:
        print(f"명령어 동기화 실패: {e}")
    print(f"✅ 로그인 완료: {bot.user}")

# ---------------------------------------------------------------------------
# 삭제 메시지 로그 (스나이프) 이벤트
# ---------------------------------------------------------------------------
@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    conn = get_conn()
    row = conn.execute("SELECT log_channel_id FROM guild_settings WHERE guild_id = ?", (message.guild.id,)).fetchone()
    conn.close()

    if row and row["log_channel_id"]:
        log_ch = message.guild.get_channel(row["log_channel_id"])
        if log_ch:
            embed = discord.Embed(
                title="🗑️ 메시지 삭제 감지",
                color=discord.Color.red(),
                timestamp=datetime.now(KST)
            )
            embed.add_field(name="작성자", value=f"{message.author.mention} (`{message.author}`)", inline=False)
            embed.add_field(name="채널", value=message.channel.mention, inline=False)
            
            content = message.content if message.content else "(텍스트 내용 없음 / 임베드 또는 첨부파일)"
            if len(content) > 1024:
                content = content[:1021] + "..."
            embed.add_field(name="삭제된 내용", value=content, inline=False)
            
            if message.attachments:
                att_names = ", ".join([att.filename for att in message.attachments])
                embed.add_field(name="첨부파일", value=att_names, inline=False)

            try:
                await log_ch.send(embed=embed)
            except Exception:
                pass

@bot.tree.command(name="로그채널설정", description="[관리자] 메시지 삭제 등 로그가 출력될 채널을 지정합니다.")
@app_commands.describe(채널="로그가 전송될 텍스트 채널")
@admin_only()
async def set_log_channel(interaction: discord.Interaction, 채널: discord.TextChannel):
    conn = get_conn()
    conn.execute(
        "INSERT INTO guild_settings (guild_id, log_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET log_channel_id = ?",
        (interaction.guild_id, 채널.id, 채널.id)
    )
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ 삭제 메시지 로그 채널이 {채널.mention} (으)로 설정되었습니다.", ephemeral=True)

# ---------------------------------------------------------------------------
# 스크림(내전/일정) 관리 시스템
# ---------------------------------------------------------------------------
class ScrimVoteView(discord.ui.View):
    def __init__(self, scrim_id: int):
        super().__init__(timeout=None)
        self.scrim_id = scrim_id

    @discord.ui.button(label="🟢 참석", style=discord.ButtonStyle.green, custom_id=f"scrim_attend_{scrim_id}")
    async def attend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_status(interaction, "attend", "참석")

    @discord.ui.button(label="🔴 불참", style=discord.ButtonStyle.danger, custom_id=f"scrim_absent_{scrim_id}")
    async def absent_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_status(interaction, "absent", "불참")

    @discord.ui.button(label="🟡 미정", style=discord.ButtonStyle.secondary, custom_id=f"scrim_pending_{scrim_id}")
    async def pending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_status(interaction, "pending", "미정")

    async def update_status(self, interaction: discord.Interaction, status: str, status_kr: str):
        user = interaction.user
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO scrim_participants (scrim_id, user_id, user_name, status) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(scrim_id, user_id) DO UPDATE SET status = ?, user_name = ?
            """,
            (self.scrim_id, user.id, user.display_name, status, status, user.display_name)
        )
        conn.commit()
        
        rows = conn.execute("SELECT user_name, status FROM scrim_participants WHERE scrim_id = ?", (self.scrim_id,)).fetchall()
        scrim_info = conn.execute("SELECT * FROM scrim_schedules WHERE id = ?", (self.scrim_id,)).fetchone()
        conn.close()

        if not scrim_info:
            await interaction.response.send_message("❌ 해당 스크림 정보를 찾을 수 없습니다.", ephemeral=True)
            return

        attends = [r["user_name"] for r in rows if r["status"] == "attend"]
        absents = [r["user_name"] for r in rows if r["status"] == "absent"]
        pendings = [r["user_name"] for r in rows if r["status"] == "pending"]

        embed = discord.Embed(
            title=f"📅 스크림 일정: {scrim_info['title']}",
            description=f"**⏰ 일시:** {scrim_info['scrim_time']}\n**📝 내용:** {scrim_info['description'] or '설명 없음'}",
            color=discord.Color.blue(),
            timestamp=datetime.now(KST)
        )
        embed.add_field(name=f"🟢 참석 ({len(attends)}명)", value=", ".join(attends) if attends else "없음", inline=False)
        embed.add_field(name=f"🔴 불참 ({len(absents)}명)", value=", ".join(absents) if absents else "없음", inline=False)
        embed.add_field(name=f"🟡 미정 ({len(pendings)}명)", value=", ".join(pendings) if pendings else "없음", inline=False)
        embed.set_footer(text=f"스크림 ID: {self.scrim_id}")

        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(f"✅ 상태가 **[{status_kr}]**(으)로 반영되었습니다.", ephemeral=True)

@bot.tree.command(name="스크림등록", description="[관리자] 새로운 스크림(내전/일정)을 생성합니다.")
@app_commands.describe(제목="스크림 제목 (예: 5vs5 내전)", 일시="진행 일시 (예: 8월 15일 저녁 9시)", 설명="상세 내용 및 규칙")
@admin_only()
async def create_scrim(interaction: discord.Interaction, 제목: str, 일시: str, 설명: str = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO scrim_schedules (guild_id, title, scrim_time, description, author_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (interaction.guild_id, 제목, 일시, 설명, interaction.user.id, now_kst_str())
    )
    scrim_id = cur.lastrowid
    conn.commit()
    conn.close()

    embed = discord.Embed(
        title=f"📅 스크림 일정: {제목}",
        description=f"**⏰ 일시:** {일시}\n**📝 내용:** {설명 or '설명 없음'}",
        color=discord.Color.blue(),
        timestamp=datetime.now(KST)
    )
    embed.add_field(name="🟢 참석 (0명)", value="없음", inline=False)
    embed.add_field(name="🔴 불참 (0명)", value="없음", inline=False)
    embed.add_field(name="🟡 미정 (0명)", value="없음", inline=False)
    embed.set_footer(text=f"스크림 ID: {scrim_id}")

    await interaction.channel.send(embed=embed, view=ScrimVoteView(scrim_id))
    await interaction.response.send_message("✅ 스크림 일정이 성공적으로 등록되었습니다.", ephemeral=True)

# ---------------------------------------------------------------------------
# 입퇴장 로그 이벤트 리스너
# ---------------------------------------------------------------------------
class MemberModView(discord.ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        
        self.add_item(discord.ui.Button(label="🔨 추방(Kick)", style=discord.ButtonStyle.danger, custom_id=f"mod_kick_{target_user_id}"))
        self.add_item(discord.ui.Button(label="🚫 차단(Ban)", style=discord.ButtonStyle.secondary, custom_id=f"mod_ban_{target_user_id}"))

@bot.event
async def on_member_join(member: discord.Member):
    conn = get_conn()
    conn.execute(
        "INSERT INTO user_join_counts (guild_id, user_id, join_count) VALUES (?, ?, 1) "
        "ON CONFLICT(guild_id, user_id) DO UPDATE SET join_count = join_count + 1",
        (member.guild.id, member.id)
    )
    join_row = conn.execute("SELECT join_count FROM user_join_counts WHERE guild_id = ? AND user_id = ?", (member.guild.id, member.id)).fetchone()
    join_count = join_row["join_count"] if join_row else 1

    row = conn.execute("SELECT welcome_channel_id FROM guild_settings WHERE guild_id = ?", (member.guild.id,)).fetchone()
    conn.close()

    if row and row["welcome_channel_id"]:
        ch = member.guild.get_channel(row["welcome_channel_id"])
        if ch:
            now_time = datetime.now(KST).strftime("%Y년 %m월 %d일 %p %I시 %M분").replace("AM", "오전").replace("PM", "오후")
            
            embed = discord.Embed(
                title="✨ 새로운 멤버 입장",
                description=f"환영합니다, {member.mention} 님! 🎉\n서버와 함께 즐거운 시간 보내세요!",
                color=discord.Color.from_rgb(85, 239, 196),
                timestamp=datetime.now(KST)
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="📌 가입 계정", value=f"`{member}`", inline=True)
            embed.add_field(name="🔄 방문 횟수", value=f"총 **{join_count}번째** 입장", inline=True)
            embed.add_field(name="👥 현재 서버 인원", value=f"`{member.guild.member_count:,}명`", inline=True)
            embed.set_footer(text=f"입장 시간: {now_time}")
            
            try:
                await ch.send(embed=embed)
            except Exception:
                pass

@bot.event
async def on_member_remove(member: discord.Member):
    conn = get_conn()
    join_row = conn.execute("SELECT join_count FROM user_join_counts WHERE guild_id = ? AND user_id = ?", (member.guild.id, member.id)).fetchone()
    join_count = join_row["join_count"] if join_row else 1

    row = conn.execute("SELECT welcome_channel_id FROM guild_settings WHERE guild_id = ?", (member.guild.id,)).fetchone()
    conn.close()

    if row and row["welcome_channel_id"]:
        ch = member.guild.get_channel(row["welcome_channel_id"])
        if ch:
            now_time = datetime.now(KST).strftime("%Y년 %m월 %d일 %p %I시 %M분").replace("AM", "오전").replace("PM", "오후")
            
            embed = discord.Embed(
                title="👋 멤버 퇴장 (관리 패널)",
                description=f"**{member}** 님이 서버를 떠나셨습니다.\n관리자만 아래 버튼으로 즉시 제재할 수 있습니다.",
                color=discord.Color.from_rgb(255, 118, 117),
                timestamp=datetime.now(KST)
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="📌 퇴장 계정", value=f"`{member}`", inline=True)
            embed.add_field(name="🔄 총 방문 횟수", value=f"총 **{join_count}회** 드나듦", inline=True)
            embed.add_field(name="👥 남은 서버 인원", value=f"`{member.guild.member_count:,}명`", inline=True)
            embed.set_footer(text=f"퇴장 시간: {now_time}")
            
            try:
                await ch.send(embed=embed, view=MemberModView(member.id))
            except Exception:
                pass

# ---------------------------------------------------------------------------
# 보안 인증 UI
# ---------------------------------------------------------------------------
class VerifyModal(discord.ui.Modal):
    def __init__(self, target_number: int):
        super().__init__(title="🔒 서버 보안 회원 인증")
        self.target_number = target_number

        self.user_answer = discord.ui.TextInput(
            label=f"아래 인증 숫자를 입력해 주세요: [{target_number}]",
            placeholder=str(target_number),
            required=True,
            min_length=4,
            max_length=4
        )
        self.add_item(self.user_answer)

    async def on_submit(self, interaction: discord.Interaction):
        typed_val = self.user_answer.value.strip()

        if typed_val == str(self.target_number):
            role = discord.utils.get(interaction.guild.roles, name=VERIFY_ROLE_NAME)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    await interaction.response.send_message(
                        f"✅ **인증 완료!** `{VERIFY_ROLE_NAME}` 역할을 받으셨습니다.", 
                        ephemeral=True
                    )
                except discord.Forbidden:
                    await interaction.response.send_message("⚠️ 봇의 권한이 부족하여 역할을 부여할 수 없습니다.", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ 서버에 `{VERIFY_ROLE_NAME}` 역할이 존재하지 않습니다.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ **인증 실패!** 입력하신 숫자가 일치하지 않습니다.", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="인증하기 🔓", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify_button_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        random_code = random.randint(1000, 9999)
        await interaction.response.send_modal(VerifyModal(random_code))

# ---------------------------------------------------------------------------
# 인터랙션 전역 처리 (추방/차단 및 역할 버튼)
# ---------------------------------------------------------------------------
class DynamicNotificationButton(discord.ui.Button):
    def __init__(self, label: str, role_id: int):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"notif_role_{role_id}")
        self.role_id = role_id

class ClearAllNotificationButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🧹 핑지우개", style=discord.ButtonStyle.secondary, custom_id="notif_role_clear_all")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        data = getattr(interaction, "data", None) or {}
        custom_id = data.get("custom_id", "") if isinstance(data, dict) else getattr(data, "custom_id", "")
        
        if custom_id.startswith("mod_kick_") or custom_id.startswith("mod_ban_"):
            if not is_admin(interaction):
                await interaction.response.send_message("❌ 이 버튼은 관리자 권한을 가진 유저만 누할 수 있습니다.", ephemeral=True)
                return

            target_id = int(custom_id.split("_")[-1])
            if custom_id.startswith("mod_kick_"):
                try:
                    await interaction.guild.kick(discord.Object(id=target_id), reason=f"로그 패널을 통한 관리자({interaction.user}) 추방")
                    await interaction.response.send_message(f"🔨 성공적으로 해당 유저를 **추방(Kick)** 조치했습니다.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ 추방 실패: {e}", ephemeral=True)
            elif custom_id.startswith("mod_ban_"):
                try:
                    await interaction.guild.ban(discord.Object(id=target_id), reason=f"로그 패널을 통한 관리자({interaction.user}) 차단")
                    await interaction.response.send_message(f"🚫 성공적으로 해당 유저를 **차단(Ban)** 조치했습니다.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ 차단 실패: {e}", ephemeral=True)
            return

        if custom_id and custom_id.startswith("notif_role_"):
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            if custom_id == "notif_role_clear_all":
                removed_roles = []
                if interaction.message and interaction.message.components:
                    for action_row in interaction.message.components:
                        for comp in action_row.children:
                            c_id = getattr(comp, "custom_id", "") or ""
                            if c_id.startswith("notif_role_") and c_id != "notif_role_clear_all":
                                r_id = int(c_id.replace("notif_role_", ""))
                                role = interaction.guild.get_role(r_id)
                                if role and role in interaction.user.roles:
                                    try:
                                        await interaction.user.remove_roles(role)
                                        removed_roles.append(role.mention)
                                    except discord.Forbidden:
                                        pass
                
                if removed_roles:
                    await interaction.followup.send(f"🧹 알림 역할이 모두 제거되었습니다: {', '.join(removed_roles)}", ephemeral=True)
                else:
                    await interaction.followup.send("🧹 제거할 알림 역할이 없습니다.", ephemeral=True)
                return

            role_id = int(custom_id.replace("notif_role_", ""))
            role = interaction.guild.get_role(role_id)
            
            if not role:
                await interaction.followup.send("❌ 부여할 역할을 서버에서 찾을 수 없습니다.", ephemeral=True)
                return

            if role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(role)
                    await interaction.followup.send(f"🔕 {role.mention} 역할이 **해제**되었습니다.", ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send("⚠️ 봇의 역할 순위가 낮아 역할을 해제할 수 없습니다.", ephemeral=True)
            else:
                try:
                    await interaction.user.add_roles(role)
                    await interaction.followup.send(f"🔔 {role.mention} 역할이 **부여**되었습니다!", ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send("⚠️ 봇의 역할 순위가 낮아 역할을 부여할 수 없습니다.", ephemeral=True)
            return

# ---------------------------------------------------------------------------
# 채널 설정 명령어
# ---------------------------------------------------------------------------
@bot.tree.command(name="입퇴장채널설정", description="[관리자] 유저 입퇴장 로그가 출력될 채널을 지정합니다.")
@app_commands.describe(채널="입퇴장 메시지가 전송될 텍스트 채널")
@admin_only()
async def set_welcome_channel(interaction: discord.Interaction, 채널: discord.TextChannel):
    conn = get_conn()
    conn.execute(
        "INSERT INTO guild_settings (guild_id, welcome_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id = ?",
        (interaction.guild_id, 채널.id, 채널.id)
    )
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ 입퇴장 로그 채널이 {채널.mention} (으)로 설정되었습니다.", ephemeral=True)

@bot.tree.command(name="입퇴장로그해제", description="[관리자] 설정된 유저 입퇴장 로그 기능을 해제합니다.")
@admin_only()
async def unset_welcome_channel(interaction: discord.Interaction):
    conn = get_conn()
    conn.execute(
        "UPDATE guild_settings SET welcome_channel_id = NULL WHERE guild_id = ?",
        (interaction.guild_id,)
    )
    conn.commit()
    conn.close()
    await interaction.response.send_message("✅ 입퇴장 로그 기능이 성공적으로 **해제**되었습니다.", ephemeral=True)

# ---------------------------------------------------------------------------
# 티켓 시스템 UI (설문 입력 포함)
# ---------------------------------------------------------------------------
class TicketModal(discord.ui.Modal, title="🎫 티켓 지원서 작성"):
    max_tier = discord.ui.TextInput(
        label="최대 티어",
        placeholder="예: 초월자 3, 다이아몬드 1 등",
        required=True,
        max_length=50
    )
    level = discord.ui.TextInput(
        label="레벨",
        placeholder="예: 250레벨",
        required=True,
        max_length=30
    )
    nickname = discord.ui.TextInput(
        label="닉네임 (#태그 포함)",
        placeholder="예: 홍길동#KR1",
        required=True,
        max_length=50
    )
    mindset = discord.ui.TextInput(
        label="마음가짐",
        placeholder="간단한 각오나 가입 동기를 적어주세요.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        conn = get_conn()
        existing = conn.execute("SELECT channel_id FROM ticket_logs WHERE guild_id = ? AND owner_id = ?", (guild.id, user.id)).fetchone()
        if existing:
            ch = guild.get_channel(existing["channel_id"])
            if ch:
                conn.close()
                await interaction.response.send_message(f"⚠️ 이미 생성된 티켓 채널이 있습니다: {ch.mention}", ephemeral=True)
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        channel_name = f"티켓-{user.name}"
        ticket_channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, reason=f"{user} 티켓 개설")

        conn.execute("INSERT INTO ticket_logs (channel_id, guild_id, owner_id, opened_at) VALUES (?, ?, ?, ?)", (ticket_channel.id, guild.id, user.id, now_kst_str()))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title=f"🎫 {user.display_name}님의 지원 티켓",
            description="작성해주신 지원서 내용입니다. 관리자의 확인을 기다려주세요!",
            color=discord.Color.blue(),
            timestamp=datetime.now(KST)
        )
        embed.add_field(name="🎮 닉네임", value=self.nickname.value, inline=False)
        embed.add_field(name="🏆 최대 티어", value=self.max_tier.value, inline=True)
        embed.add_field(name="⭐ 레벨", value=self.level.value, inline=True)
        embed.add_field(name="💬 마음가짐", value=self.mindset.value, inline=False)

        await ticket_channel.send(content=f"{user.mention} 님, 티켓이 생성되었습니다.", embed=embed, view=TicketControlView())
        await interaction.response.send_message(f"✅ 티켓 채널이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 티켓 열기", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal())

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 티켓 닫기", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = interaction.channel_id
        conn = get_conn()
        t_row = conn.execute("SELECT * FROM ticket_logs WHERE channel_id = ?", (channel_id,)).fetchone()
        
        conn.execute("DELETE FROM ticket_logs WHERE channel_id = ?", (channel_id,))
        conn.commit()
        conn.close()

        await interaction.response.send_message("📢 **티켓이 종료되어 채널이 곧 삭제됩니다.**")

        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason="티켓 닫기")
        except Exception:
            pass

@bot.tree.command(name="티켓패널", description="[관리자] 티켓 패널을 전송합니다.")
@admin_only()
async def ticket_panel(interaction: discord.Interaction):
    server_name = interaction.guild.name if interaction.guild else "서버"
    embed = discord.Embed(
        title=f"🎫 {server_name} 지원 및 문의 티켓",
        description="아래 **[🎫 티켓 열기]** 버튼을 누르면 설문창이 뜨며, 작성 완료 시 전용 채널이 생성됩니다.",
        color=discord.Color.green()
    )
    await interaction.channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message("✅ 티켓 패널이 생성되었습니다.", ephemeral=True)

@bot.tree.command(name="인증패널", description="[관리자] 보안 회원 인증 패널을 전송합니다.")
@admin_only()
async def verify_panel(interaction: discord.Interaction):
    server_name = interaction.guild.name if interaction.guild else "서버"
    embed = discord.Embed(
        title=f"🔒 {server_name} 회원 인증",
        description="아래 **[인증하기 🔓]** 버튼을 누른 후, 안내되는 4자리 숫자를 입력해 주세요.",
        color=discord.Color.green()
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("✅ 인증 패널이 생성되었습니다.", ephemeral=True)

@bot.tree.command(name="알림패널생성", description="[관리자] 기본 알림 설정 패널을 생성합니다.")
@admin_only()
async def create_notification_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(
        title="🔔 알림 역할 설정",
        description="받으실 알림을 눌러주세요\n____________________",
        color=discord.Color.gold()
    )
    view = discord.ui.View(timeout=None)
    
    await interaction.channel.send(embed=embed, view=view)
    await interaction.followup.send("✅ 알림 패널이 생성되었습니다!", ephemeral=True)

@bot.tree.command(name="알림버튼추가", description="[관리자] 채널의 가장 마지막 알림 패널에 역할 버튼을 추가합니다.")
@app_commands.describe(버튼이름="버튼에 표시될 이름", 지급역할="지급할 역할(@역할)")
@admin_only()
async def add_notification_button(interaction: discord.Interaction, 버튼이름: str, 지급역할: discord.Role):
    await interaction.response.defer(ephemeral=True)
    
    target_msg = None
    async for message in interaction.channel.history(limit=20):
        if message.author == bot.user and message.embeds:
            if "알림 역할 설정" in message.embeds[0].title:
                target_msg = message
                break

    if not target_msg:
        await interaction.followup.send("❌ 이 채널에서 `🔔 알림 역할 설정` 패널 메시지를 찾지 못했습니다.", ephemeral=True)
        return

    view = discord.ui.View.from_message(target_msg) if target_msg.components else discord.ui.View(timeout=None)
    view.timeout = None
    view.add_item(DynamicNotificationButton(label=버튼이름, role_id=지급역할.id))
    
    await target_msg.edit(view=view)
    await interaction.followup.send(f"✅ 가장 최근 알림 패널에 **[{버튼이름}]** 버튼이 추가되었습니다!", ephemeral=True)

@bot.tree.command(name="핑지우개버튼추가", description="[관리자] 채널의 가장 마지막 알림 패널에 핑지우개 버튼을 추가합니다.")
@admin_only()
async def add_clear_button(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    target_msg = None
    async for message in interaction.channel.history(limit=20):
        if message.author == bot.user and message.embeds:
            if "알림 역할 설정" in message.embeds[0].title:
                target_msg = message
                break

    if not target_msg:
        await interaction.followup.send("❌ 이 채널에서 `🔔 알림 역할 설정` 패널 메시지를 찾지 못했습니다.", ephemeral=True)
        return

    view = discord.ui.View.from_message(target_msg) if target_msg.components else discord.ui.View(timeout=None)
    view.timeout = None
    view.add_item(ClearAllNotificationButton())
    
    await target_msg.edit(view=view)
    await interaction.followup.send("✅ 가장 최근 알림 패널에 **🧹 핑지우개** 버튼이 추가되었습니다!", ephemeral=True)

# ---------------------------------------------------------------------------
# 봇 실행
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit("❌ DISCORD_TOKEN이 설정되지 않았습니다. .env 환경변수를 설정하거나 토큰을 입력하세요.")
    bot.run(TOKEN)
