"""Process-wide discord.py Gateway reconnect guard."""
import asyncio

try:
    import discord
except Exception:
    discord = None

if discord is not None and not getattr(discord.Client, "_best11_gateway_guard", False):
    _original_connect = discord.Client.connect

    async def _resilient_connect(self, *, reconnect=True):
        while not self.is_closed():
            try:
                await _original_connect(self, reconnect=reconnect)
                return
            except AttributeError as exc:
                if reconnect and getattr(self, "ws", None) is None and "sequence" in str(exc):
                    print("[BEST-GATEWAY] websocket state lost; retrying with a fresh connection in 3s")
                    await asyncio.sleep(3)
                    continue
                raise

    discord.Client.connect = _resilient_connect
    discord.Client._best11_gateway_guard = True
