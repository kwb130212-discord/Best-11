# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import os
import random
import urllib.error
import urllib.request
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands


@dataclass
class DebateSession:
    guild_id: int
    channel_id: int
    owner_id: int
    topic: str


SESSIONS: dict[str, DebateSession] = {}


def new_code() -> str:
    for _ in range(100):
        code = f"{random.randint(0, 9999):04d}"
        if code not in SESSIONS:
            return code
    raise RuntimeError("사용 가능한 4자리 토론 코드가 없습니다.")


def ask_ai(system: str, prompt: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
    url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions").rstrip("/")
    if url.endswith("/responses"):
        endpoint = url
        payload = {"model": model, "instructions": system, "input": prompt}
    else:
        endpoint = url
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.7,
        }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"AI API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI API 연결 실패: {exc.reason}") from exc

    if "output" in data:
        parts = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    parts.append(text)
        result = "\n".join(parts).strip()
    else:
        result = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if not result:
        raise RuntimeError("AI 응답이 비어 있습니다.")
    return result


async def run_debate(topic: str) -> str:
    system = """너는 Discord AI 토론 시스템의 진행자다. 주제에 대해 찬성 AI와 반대 AI가 각각 주장하고 서로 반론한 뒤, 마지막에 판정 AI가 핵심 쟁점을 중립적으로 정리한다. 사실이 필요한 내용은 확실하지 않으면 추측하지 말고 불확실성을 표시한다. 정치적 주제라면 특정 후보·정당·정책을 지지하거나 반대하도록 유도하지 말고 사실과 쟁점을 균형 있게 정리한다. 출력은 한국어로 간결하게 작성한다."""
    prompt = f"""다음 주제로 AI 토론을 진행해라.\n\n주제: {topic}\n\n형식:\n[찬성 AI]\n핵심 주장 2~3개\n\n[반대 AI]\n핵심 반론 2~3개\n\n[상호 반론]\n찬성 AI의 반론 1개와 반대 AI의 재반론 1개\n\n[판정 AI]\n확인된 사실, 핵심 쟁점, 의견이 갈리는 지점, 추가로 확인할 사항을 중립적으로 정리\n\n전체를 1800자 이내로 작성해라."""
    return await asyncio.to_thread(ask_ai, system, prompt)


async def send_long(interaction: discord.Interaction, text: str) -> None:
    chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)] or ["(응답 없음)"]
    await interaction.response.send_message(chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


class AIDebateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ai코딩", description="AI 코딩/토론 세션을 만들고 4자리 코드를 발급합니다.")
    @app_commands.describe(주제="AI가 토론할 코딩 또는 기술 주제")
    async def ai_coding(self, interaction: discord.Interaction, 주제: str) -> None:
        topic = 주제.strip()
        if not topic:
            await interaction.response.send_message("❌ 주제를 입력해주세요.", ephemeral=True)
            return
        code = new_code()
        SESSIONS[code] = DebateSession(interaction.guild_id, interaction.channel_id, interaction.user.id, topic)
        embed = discord.Embed(title="🤖 AI 코딩 토론 세션 생성", color=discord.Color.blurple())
        embed.add_field(name="주제", value=topic[:1024], inline=False)
        embed.add_field(name="토론 코드", value=f"`{code}`", inline=True)
        embed.add_field(name="다음 단계", value=f"`/토론 코드번호:{code}`", inline=False)
        embed.set_footer(text="4자리 코드는 이 봇 프로세스가 실행 중인 동안 유효합니다.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="토론", description="4자리 코드의 AI 토론을 실행합니다.")
    @app_commands.describe(코드번호="/ai코딩에서 발급된 4자리 코드")
    async def debate(self, interaction: discord.Interaction, 코드번호: str) -> None:
        code = 코드번호.strip()
        if len(code) != 4 or not code.isdigit():
            await interaction.response.send_message("❌ 토론 코드는 정확히 4자리 숫자여야 합니다.", ephemeral=True)
            return
        session = SESSIONS.get(code)
        if not session:
            await interaction.response.send_message("❌ 존재하지 않거나 만료된 토론 코드입니다.", ephemeral=True)
            return
        if session.guild_id != interaction.guild_id:
            await interaction.response.send_message("❌ 이 서버에서 생성된 토론 코드가 아닙니다.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            result = await run_debate(session.topic)
        except Exception as exc:
            await interaction.followup.send(f"❌ AI 토론 실행 실패: `{exc}`")
            return
        await interaction.followup.send(f"**🤖 AI 토론 결과 — `{code}`**\n**주제:** {session.topic}")
        chunks = [result[i:i + 1900] for i in range(0, len(result), 1900)]
        for chunk in chunks:
            await interaction.followup.send(chunk)
        SESSIONS.pop(code, None)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIDebateCog(bot))
