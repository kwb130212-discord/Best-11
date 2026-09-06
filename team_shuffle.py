# -*- coding: utf-8 -*-
"""스크림 참석자 자동 팀 배정 기능."""
import random
import discord
from discord import app_commands

SCRIM_ROLE_NAME = "정기내전(스크림)참석"


def setup_team_shuffle(bot, get_conn):
    @bot.tree.command(name="팀짜기", description="현재 스크림 참석 인원으로 랜덤 팀을 구성합니다.")
    async def team_shuffle(interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("❌ 서버에서만 사용할 수 있습니다.", ephemeral=True)

        # 가장 최근에 등록된 스크림을 현재 스크림으로 간주합니다.
        conn = get_conn()
        scrim = conn.execute(
            "SELECT id, title, scrim_time FROM scrim_schedules WHERE guild_id=? ORDER BY id DESC LIMIT 1",
            (interaction.guild.id,),
        ).fetchone()
        if not scrim:
            conn.close()
            return await interaction.response.send_message("❌ 등록된 스크림이 없습니다.", ephemeral=True)

        rows = conn.execute(
            "SELECT user_id FROM scrim_participants WHERE scrim_id=? AND status='attend'",
            (scrim["id"],),
        ).fetchall()
        conn.close()

        members = []
        seen = set()
        for row in rows:
            member = interaction.guild.get_member(row["user_id"])
            if member and not member.bot and member.id not in seen:
                members.append(member)
                seen.add(member.id)

        # 역할도 확인하여, 버튼으로 참석 처리된 최신 상태와 실제 멤버 상태가 어긋난 경우를 방지합니다.
        role = discord.utils.get(interaction.guild.roles, name=SCRIM_ROLE_NAME)
        if role:
            role_ids = {m.id for m in role.members if not m.bot}
            members = [m for m in members if m.id in role_ids]

        if len(members) < 2:
            return await interaction.response.send_message(
                f"❌ 팀을 만들려면 스크림 참석 인원이 최소 2명 필요합니다. (현재 {len(members)}명)",
                ephemeral=True,
            )

        random.shuffle(members)
        half = (len(members) + 1) // 2
        team_a = members[:half]
        team_b = members[half:]

        def mentions(team):
            return "\n".join(f"{idx}. {member.mention}" for idx, member in enumerate(team, 1))

        embed = discord.Embed(
            title="⚔️ 스크림 랜덤 팀 배정",
            description=(
                f"**스크림:** {scrim['title']}\n"
                f"**일시:** {scrim['scrim_time']}\n"
                f"**참석 인원:** {len(members)}명\n\n"
                "참석자로 등록된 인원만 자동으로 배정했습니다."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name=f"🔵 TEAM A ({len(team_a)}명)", value=mentions(team_a), inline=True)
        embed.add_field(name=f"🔴 TEAM B ({len(team_b)}명)", value=mentions(team_b), inline=True)
        embed.set_footer(text="/팀짜기 • 다시 실행하면 새롭게 랜덤 배정됩니다.")

        await interaction.response.send_message(embed=embed)
