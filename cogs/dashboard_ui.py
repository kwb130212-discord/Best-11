# -*- coding: utf-8 -*-
"""BEST-11 프리미엄 통합 대시보드 UI."""
import discord

from premium_ui import PRIMARY, SUCCESS, WARNING, DANGER


class DashboardSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="유튜브 · 크리에이터", value="creator", emoji="🎬", description="영상 알림과 크리에이터 기능"),
            discord.SelectOption(label="클랜 · 커뮤니티", value="clan", emoji="🏆", description="클랜 운영과 랭킹 기능"),
            discord.SelectOption(label="티켓 · 지원", value="ticket", emoji="🎫", description="문의 티켓과 처리 현황"),
            discord.SelectOption(label="보안 · 관리", value="security", emoji="🛡️", description="인증과 서버 관리 기능"),
            discord.SelectOption(label="스크림 · 경기", value="scrim", emoji="⚔️", description="내전 일정과 참가 관리"),
        ]
        super().__init__(placeholder="원하는 기능 영역을 선택하세요", min_values=1, max_values=1, options=options, custom_id="best11_dashboard_select")

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        data = {
            "creator": ("🎬 유튜브 · 크리에이터", "자동 영상 공지, 알림 역할, 크리에이터 공지 기능을 한 곳에서 관리합니다.", SUCCESS),
            "clan": ("🏆 클랜 · 커뮤니티", "클랜 운영, 모집, 랭킹 및 커뮤니티 기능을 빠르게 확인합니다.", PRIMARY),
            "ticket": ("🎫 티켓 · 지원", "문의 티켓을 열고, 현재 처리 현황과 기록을 관리합니다.", WARNING),
            "security": ("🛡️ 보안 · 관리", "회원 인증, 로그, 제재 등 서버 관리 기능을 확인합니다.", DANGER),
            "scrim": ("⚔️ 스크림 · 경기", "스크림 일정과 참가 상태를 관리합니다.", PRIMARY),
        }
        title, description, color = data[key]
        embed = discord.Embed(title=title, description=description, color=color)
        commands = sorted({command.qualified_name for command in self.bot.tree.get_commands()})
        groups = {
            "creator": [x for x in commands if any(k in x for k in ("유튜브", "영상", "공지"))],
            "clan": [x for x in commands if any(k in x for k in ("클랜", "랭킹", "모집"))],
            "ticket": [x for x in commands if "티켓" in x],
            "security": [x for x in commands if any(k in x for k in ("인증", "로그", "제재", "보안"))],
            "scrim": [x for x in commands if "스크림" in x],
        }
        names = groups[key]
        embed.add_field(name="사용 가능한 명령어", value="\n".join(f"`/{name}`" for name in names[:15]) or "현재 등록된 명령어가 없습니다.", inline=False)
        embed.set_footer(text="BEST-11  •  Premium Control Center")
        await interaction.response.edit_message(embed=embed, view=self.view)


class DashboardView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.add_item(DashboardSelect(bot))


def setup_dashboard(bot):
    @bot.tree.command(name="대시보드", description="BEST-11의 모든 주요 기능을 한눈에 확인합니다.")
    async def dashboard(interaction: discord.Interaction):
        guild = interaction.guild
        member_count = guild.member_count if guild else 0
        embed = discord.Embed(
            title="✦ BEST-11  CONTROL CENTER",
            description=(
                "### 서버 운영을 한 화면에서\n"
                "유튜브 · 클랜 · 티켓 · 보안 · 스크림 기능을 카테고리별로 빠르게 이동할 수 있습니다.\n\n"
                f"**서버**  `{guild.name if guild else 'DM'}`\n"
                f"**멤버**  `{member_count:,}명`\n\n"
                "아래 메뉴에서 영역을 선택하면 해당 기능만 정리해서 보여줍니다."
            ),
            color=PRIMARY,
        )
        embed.add_field(name="🎬 CREATOR", value="자동 영상 공지 · 알림", inline=True)
        embed.add_field(name="🏆 CLAN", value="모집 · 랭킹 · 운영", inline=True)
        embed.add_field(name="🎫 SUPPORT", value="티켓 · 문의 관리", inline=True)
        embed.add_field(name="🛡️ SECURITY", value="인증 · 로그 · 관리", inline=True)
        embed.add_field(name="⚔️ SCRIM", value="일정 · 참가 관리", inline=True)
        embed.add_field(name="⚡ STATUS", value="정상 작동 중", inline=True)
        embed.set_footer(text="BEST-11  •  Premium Control Center")
        await interaction.response.send_message(embed=embed, view=DashboardView(bot))

    print("[BEST] premium dashboard loaded")
