# -*- coding: utf-8 -*-
"""NVIDIA NIM 기반 커뮤니티 분쟁 판정 시스템."""
import asyncio
import json
import os
import urllib.error
import urllib.request

import discord
from discord import app_commands

API_URL = os.getenv("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
MODEL = os.getenv("NVIDIA_JUDGE_MODEL", "nvidia/nemotron-3-super-120b-a12b")
SYSTEM_PROMPT = """너는 Discord 서버의 '커뮤니티 분쟁 판정 보조 AI'다.
실제 법원 판사나 변호사가 아니며 법적 효력이 있는 판결을 내리지 않는다.
제공된 원고, 피고, 사실관계만 바탕으로 양측에 동일한 기준을 적용하고, 정보가 부족하면 부족하다고 명시한다.
욕설, 인신공격, 추측은 판단 근거로 사용하지 않는다. 사실과 주장과 추론을 구분한다.
한쪽을 무조건 편들지 말고 중립적으로 판단한다.
최종 답변은 한국어로 작성하며 다음 항목을 반드시 포함한다:
- 판정 요약
- 사실관계 정리
- 판단 근거
- 책임 비율 또는 책임 없음(근거가 있을 때만)
- 권고 조치
- 불확실성/추가로 필요한 정보
법률 자문이나 실제 법적 판결처럼 표현하지 않는다."""


def _request_judgment(prompt: str) -> str:
    if not API_KEY:
        raise RuntimeError("NVIDIA_API_KEY가 설정되지 않았습니다.")
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1400,
        "stream": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"NVIDIA API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"NVIDIA API 연결 실패: {exc.reason}") from exc
    choices = payload.get("choices") or []
    if not choices or not choices[0].get("message", {}).get("content"):
        raise RuntimeError("NVIDIA API가 비어 있는 판정 결과를 반환했습니다.")
    return choices[0]["message"]["content"].strip()


def _next_case_number(get_conn, guild_id: int) -> int:
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT COALESCE(MAX(case_no), 0) + 1 AS next_no FROM ai_judgments WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        case_no = int(row["next_no"])
        conn.rollback()
        return case_no
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _save_case(get_conn, guild_id: int, case_no: int, plaintiff: str, defendant: str, incident: str, result: str, requester_id: int) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO ai_judgments
        (guild_id, case_no, plaintiff, defendant, incident, result, requester_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (guild_id, case_no, plaintiff, defendant, incident, result, requester_id),
    )
    conn.commit()
    conn.close()


def setup_nvidia_judge(bot, get_conn, admin_only):
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_judgments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        case_no INTEGER NOT NULL,
        plaintiff TEXT NOT NULL,
        defendant TEXT NOT NULL,
        incident TEXT NOT NULL,
        result TEXT NOT NULL,
        requester_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(guild_id, case_no)
    )""")
    conn.commit()
    conn.close()

    @bot.tree.command(name="판결", description="AI가 커뮤니티 분쟁 내용을 중립적으로 분석합니다.")
    @app_commands.describe(
        원고="문제를 제기한 사람 또는 측",
        피고="문제의 대상이 된 사람 또는 측",
        있었던일="시간순 사실관계와 양측 주장을 구체적으로 적어주세요.",
    )
    async def judgment(interaction: discord.Interaction, 원고: str, 피고: str, 있었던일: str):
        if interaction.guild is None:
            await interaction.response.send_message("❌ 서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        원고, 피고, 있었던일 = 원고.strip(), 피고.strip(), 있었던일.strip()
        if len(원고) > 200 or len(피고) > 200 or len(있었던일) > 5000:
            await interaction.response.send_message("❌ 입력이 너무 깁니다. 원고/피고는 200자, 있었던 일은 5000자 이내로 작성해주세요.", ephemeral=True)
            return
        if not 원고 or not 피고 or not 있었던일:
            await interaction.response.send_message("❌ 원고, 피고, 있었던 일을 모두 입력해주세요.", ephemeral=True)
            return
        if 원고 == 피고:
            await interaction.response.send_message("❌ 원고와 피고를 동일하게 입력할 수 없습니다.", ephemeral=True)
            return
        if not API_KEY:
            await interaction.response.send_message("❌ NVIDIA_API_KEY가 설정되지 않았습니다. 관리자에게 환경변수 설정을 요청하세요.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            prompt = (
                f"원고: {원고}\n"
                f"피고: {피고}\n"
                f"있었던 일: {있었던일}\n\n"
                "위 사건을 커뮤니티 운영 관점에서 중립적으로 분석하고 판정하라. "
                "확인되지 않은 사실은 사실처럼 단정하지 말고, 증거가 없으면 그 점을 명시하라."
            )
            result = await asyncio.to_thread(_request_judgment, prompt)
            case_no = await asyncio.to_thread(_next_case_number, get_conn, interaction.guild.id)
            await asyncio.to_thread(
                _save_case,
                get_conn,
                interaction.guild.id,
                case_no,
                원고,
                피고,
                있었던일,
                result,
                interaction.user.id,
            )
        except Exception as exc:
            print(f"[NVIDIA-JUDGE] failed: {type(exc).__name__}: {exc}")
            await interaction.followup.send(f"❌ 판정 생성에 실패했습니다: `{type(exc).__name__}`", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📖 AI 판결문 · 판결번호-{case_no:04d}",
            description="실제 법적 판결이 아닌 서버 내 분쟁을 위한 AI 분석 결과입니다.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="원고", value=원고, inline=True)
        embed.add_field(name="피고", value=피고, inline=True)
        embed.add_field(name="있었던 일", value=있었던일[:1024], inline=False)
        embed.add_field(name="⚖️ 판정", value=result[:5900], inline=False)
        embed.set_footer(text="AI 판정은 참고용이며 최종적인 서버 운영 판단은 관리자에게 있습니다.")
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="판결조회", description="발급된 AI 판결번호를 조회합니다.")
    @app_commands.describe(판결번호="예: 0001")
    async def judgment_lookup(interaction: discord.Interaction, 판결번호: int):
        if interaction.guild is None:
            await interaction.response.send_message("❌ 서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        if 판결번호 < 1:
            await interaction.response.send_message("❌ 올바른 판결번호를 입력하세요.", ephemeral=True)
            return
        conn = get_conn()
        row = conn.execute(
            "SELECT case_no, plaintiff, defendant, incident, result FROM ai_judgments WHERE guild_id = ? AND case_no = ?",
            (interaction.guild.id, 판결번호),
        ).fetchone()
        conn.close()
        if row is None:
            await interaction.response.send_message(f"❌ 판결번호-{판결번호:04d}를 찾을 수 없습니다.", ephemeral=True)
            return
        embed = discord.Embed(title=f"📖 판결문 · 판결번호-{row['case_no']:04d}", color=discord.Color.blurple())
        embed.add_field(name="원고", value=row["plaintiff"], inline=True)
        embed.add_field(name="피고", value=row["defendant"], inline=True)
        embed.add_field(name="있었던 일", value=row["incident"][:1024], inline=False)
        embed.add_field(name="⚖️ 판정", value=row["result"][:5900], inline=False)
        embed.set_footer(text="AI 분석 기록 · 실제 법적 효력 없음")
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="판결명령어", description="AI 판결 시스템 명령어를 확인합니다.")
    async def judgment_help(interaction: discord.Interaction):
        embed = discord.Embed(title="📖 AI 판결 시스템", color=discord.Color.blurple())
        embed.description = (
            "`/판결 원고: 피고: 있었던일:` → NVIDIA AI 분석 후 판결번호 발급\n"
            "`/판결조회 판결번호:` → 저장된 판결문 조회\n\n"
            "판결번호는 서버별로 0001부터 순서대로 발급됩니다."
        )
        embed.set_footer(text="실제 법적 판결이 아닌 커뮤니티 운영용 참고 결과")
        await interaction.response.send_message(embed=embed)
