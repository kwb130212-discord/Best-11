# -*- coding: utf-8 -*-
"""스크림 참석자 자동 2팀 배정 기능."""
import random
import discord
from discord import app_commands

SCRIM_ROLE_NAME = "정기내전(스크림)참석"


def setup_team_shuffle(bot, get_conn):
    @bot.tree.command(name="팀짜기", description="현재 스크림 참석 인원을 A팀과 B팀으로 랜덤 배정합니다.")
    async def team_shuffle(interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("❌ 서버에서만 사용할 수 있습니다.", ephemeral=True)

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

        role = discord.utils.get(interaction.guild.roles, name=SCRIM_ROLE_NAME)
        if role:
            role_ids = {m.id for m in role.members if not m.bot}
            members = [m for m in members if m.id in role_ids]

        if len(members) < 2:
            return await interaction.response.send_message(
                f"❌ 팀을 만들려면 스크림 참석 인원이 최소 2명 필요합니다. (현재 {len(members)}명)",
                ephemeral=True,
            )

        # 항상 정확히 A팀/B팀 두 팀으로만 나눕니다. 인원이 홀수면 A팀이 1명 더 많습니다.
        random.shuffle(members)
        team_a = members[::2]
        team_b = members[1::2]

        # 3명, 5명 등 홀수일 때 A팀에 1명 더 들어가도록 보정합니다.
        if len(team_a) < len(team_b):
            team_a, team_b = team_b, team_a

        def mentions(team):
            return "\n".join(f"{idx}. {member.mention}" for idx, member in enumerate(team, 1)) or "없음"

        embed = discord.Embed(
            title="⚔️ 스크림 팀 배정",
            description=(
                f"**스크림:** {scrim['title']}\n"
                f"**일시:** {scrim['scrim_time']}\n"
                f"**참석 인원:** {len(members)}명\n\n"
                "스크림 참석자로 등록된 인원만 랜덤 배정했습니다."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name=f"🔵 A팀 ({len(team_a)}명)", value=mentions(team_a), inline=True)
        embed.add_field(name=f"🔴 B팀 ({len(team_b)}명)", value=mentions(team_b), inline=True)
        embed.set_footer(text="/팀짜기 • 다시 실행하면 새롭게 랜덤 배정됩니다.")

        await interaction.response.send_message(embed=embed)
