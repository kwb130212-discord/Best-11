# -*- coding: utf-8 -*-
"""루에드 유튜브 전용 알림 영역."""
import asyncio
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands

KST = timezone(timedelta(hours=9))
CHANNEL_ID = "UCUPmRarC5IUyph8-tA3akUg"
ROLE_NAME = os.getenv("YOUTUBE_NOTIFY_ROLE_NAME", "유튜브 알림받기")
SUBSCRIBER_ROLE_NAME = os.getenv("ROUED_SUBSCRIBER_ROLE_NAME", "루에드 구독자")
CATEGORY_NAME = "유튜브 알림"
OPTIN_CHANNEL = "유튜브-알림받기"
VIDEO_CHANNEL = "유튜브-새영상"
SUBSCRIBE_VERIFY_CHANNEL = "루에드-구독인증"


def setup_youtube_alerts(bot, get_conn, admin_only):
    def init_db():
        c = get_conn()
        c.execute("CREATE TABLE IF NOT EXISTS roued_yt_state(guild_id INTEGER PRIMARY KEY,last_video_id TEXT)")
        c.commit()
        c.close()

    init_db()

    def get_role(guild):
        return discord.utils.get(guild.roles, name=ROLE_NAME)

    async def ensure_role(guild):
        role = get_role(guild)
        if role:
            return role
        try:
            return await guild.create_role(name=ROLE_NAME, reason="루에드 유튜브 알림 역할")
        except (discord.Forbidden, discord.HTTPException):
            return None

    def get_subscriber_role(guild):
        return discord.utils.get(guild.roles, name=SUBSCRIBER_ROLE_NAME)

    async def ensure_subscriber_role(guild):
        role = get_subscriber_role(guild)
        if role:
            return role
        try:
            return await guild.create_role(name=SUBSCRIBER_ROLE_NAME, reason="루에드 구독 인증 역할")
        except (discord.Forbidden, discord.HTTPException):
            return None

    class AlertView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="🔔 유튜브 알림 켜기", style=discord.ButtonStyle.success, custom_id="roued_yt_on")
        async def on_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            role = await ensure_role(interaction.guild)
            if not role:
                return await interaction.response.send_message("❌ 알림 역할을 만들 권한이 없습니다.", ephemeral=True)
            try:
                await interaction.user.add_roles(role, reason="루에드 유튜브 알림 켜기")
                await interaction.response.send_message(f"🔔 **{ROLE_NAME}** 역할을 부여했습니다. 새 영상 알림을 받습니다.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ 봇의 역할이 알림 역할보다 아래에 있습니다.", ephemeral=True)

        @discord.ui.button(label="🔕 유튜브 알림 끄기", style=discord.ButtonStyle.danger, custom_id="roued_yt_off")
        async def off_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            role = get_role(interaction.guild)
            if not role:
                return await interaction.response.send_message("ℹ️ 현재 알림이 꺼져 있습니다.", ephemeral=True)
            try:
                await interaction.user.remove_roles(role, reason="루에드 유튜브 알림 끄기")
                await interaction.response.send_message(f"🔕 **{ROLE_NAME}** 역할을 제거했습니다. 새 영상 알림을 받지 않습니다.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ 봇의 역할이 알림 역할보다 아래에 있습니다.", ephemeral=True)

    @bot.tree.command(name="유튜브알림패널", description="[관리자] 루에드 유튜브 전용 알림 채널과 패널을 만듭니다.")
    @admin_only()
    async def youtube_panel(interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ 서버에서만 사용할 수 있습니다.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if not category:
            category = await guild.create_category(CATEGORY_NAME, reason="루에드 유튜브 알림 전용 영역")

        optin = discord.utils.get(category.text_channels, name=OPTIN_CHANNEL)
        video = discord.utils.get(category.text_channels, name=VIDEO_CHANNEL)
        if not optin:
            optin = await guild.create_text_channel(OPTIN_CHANNEL, category=category, reason="유튜브 알림 신청 채널")
        if not video:
            video = await guild.create_text_channel(VIDEO_CHANNEL, category=category, reason="유튜브 새영상 채널")

        role = await ensure_role(guild)
        if not role:
            return await interaction.followup.send(f"❌ `{ROLE_NAME}` 역할 생성에 실패했습니다.", ephemeral=True)

        await ensure_subscriber_role(guild)
        c = get_conn()
        c.execute("INSERT INTO best_yt_settings(guild_id,notify_channel_id,enabled) VALUES(?,?,1) ON CONFLICT(guild_id) DO UPDATE SET notify_channel_id=excluded.notify_channel_id,enabled=1", (guild.id, video.id))
        c.execute("INSERT OR IGNORE INTO roued_yt_state(guild_id,last_video_id) VALUES(?,NULL)", (guild.id,))
        c.commit()
        c.close()

        embed = discord.Embed(title="📺 루에드 유튜브 알림", description="루에드의 새 영상 알림을 받고 싶다면 아래 버튼을 눌러주세요.\n\n🔔 **켜기** → `유튜브 알림받기` 역할 부여\n🔕 **끄기** → 역할 제거\n\n새 영상은 `유튜브-새영상` 채널에 자동으로 올라옵니다.\n\n📸 `루에드-구독인증` 채널에 유튜브 구독 인증 사진을 올리면 **루에드 구독자** 역할을 자동 지급합니다.", color=discord.Color.red())
        embed.add_field(name="채널", value="[루에드 유튜브](https://youtube.com/channel/UCUPmRarC5IUyph8-tA3akUg)", inline=False)
        embed.set_footer(text="알림은 언제든지 버튼으로 변경할 수 있습니다.")
        await optin.send(embed=embed, view=AlertView())
        await interaction.followup.send(f"✅ 전용 영역을 준비했습니다. {optin.mention} / {video.mention}", ephemeral=True)

    async def latest_video():
        url = "https://www.youtube.com/feeds/videos.xml?channel_id=" + urllib.parse.quote(CHANNEL_ID)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = await asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=10).read())
            root = ET.fromstring(data)
            ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
            entry = root.find("a:entry", ns)
            if entry is None:
                return None
            vid = entry.findtext("yt:videoId", namespaces=ns)
            title = entry.findtext("a:title", namespaces=ns) or "새 영상"
            published = entry.findtext("a:published", namespaces=ns) or ""
            return {"id": vid, "title": title, "published": published, "url": f"https://www.youtube.com/watch?v={vid}"} if vid else None
        except Exception as exc:
            print("[ROUED-YOUTUBE]", exc)
            return None

    async def poll_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            try:
                video = await latest_video()
                if video:
                    c = get_conn()
                    states = c.execute("SELECT * FROM roued_yt_state").fetchall()
                    for state in states:
                        guild = bot.get_guild(state["guild_id"])
                        if not guild:
                            continue
                        if not state["last_video_id"]:
                            c.execute("UPDATE roued_yt_state SET last_video_id=? WHERE guild_id=?", (video["id"], guild.id))
                            continue
                        if state["last_video_id"] == video["id"]:
                            continue
                        settings = c.execute("SELECT * FROM best_yt_settings WHERE guild_id=? AND enabled=1", (guild.id,)).fetchone()
                        if not settings:
                            continue
                        channel = guild.get_channel(settings["notify_channel_id"])
                        role = get_role(guild)
                        if channel and role:
                            embed = discord.Embed(title="🆕 루에드 유튜브 새 영상", description=f"**{video['title']}**\n\n▶️ [새 영상 보러가기]({video['url']})", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
                            if video["published"]:
                                embed.add_field(name="업로드", value=video["published"].replace("T", " ").replace("Z", " UTC"), inline=False)
                            embed.set_footer(text="루에드 유튜브 자동 알림")
                            await channel.send(content=role.mention, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))
                        c.execute("UPDATE roued_yt_state SET last_video_id=? WHERE guild_id=?", (video["id"], guild.id))
                    c.commit()
                    c.close()
            except Exception as exc:
                print("[ROUED-YOUTUBE-LOOP]", exc)
            await asyncio.sleep(max(30, int(os.getenv("YOUTUBE_POLL_SECONDS", "120"))))

    async def subscriber_verification(message: discord.Message):
        if message.author.bot or not message.guild or message.channel.name != SUBSCRIBE_VERIFY_CHANNEL:
            return
        images = [a for a in message.attachments if (a.content_type or "").lower().startswith("image/") or a.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))]
        if not images:
            return
        role = await ensure_subscriber_role(message.guild)
        if role is None:
            return
        try:
            if role not in message.author.roles:
                await message.author.add_roles(role, reason="루에드 구독 인증 사진 업로드")
            await message.add_reaction("✅")
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"[ROUED-SUBSCRIBER] role update failed for {message.author}: {exc}")

    bot.add_listener(subscriber_verification, "on_message")

    async def ready():
        init_db()
        for guild in bot.guilds:
            c = get_conn()
            c.execute("INSERT OR IGNORE INTO roued_yt_state(guild_id,last_video_id) VALUES(?,NULL)", (guild.id,))
            c.commit()
            c.close()
        if not getattr(bot, "_roued_yt_task", None) or bot._roued_yt_task.done():
            bot._roued_yt_task = asyncio.create_task(poll_loop())
        try:
            bot.add_view(AlertView())
        except ValueError:
            pass

    bot.add_listener(ready, "on_ready")
    print("[BEST] 루에드 유튜브 전용 알림 + 구독 인증 시스템 loaded")
