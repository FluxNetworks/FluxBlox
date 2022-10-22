from ..structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from ..constants import TOPGG_API, DBL_API, RELEASE, SHARD_RANGE, SHARD_COUNT # pylint: disable=import-error, no-name-in-module
from ..secrets import TOPGG_KEY, DBL_KEY # pylint: disable=import-error, no-name-in-module
import aiohttp



fetch = Fluxblox.get_module("utils", attrs="fetch")


@Fluxblox.module
class DBL(Fluxblox.Module):
    def __init__(self):
        pass

    async def post_topgg(self):
        url = f"{TOPGG_API}/bots/{Fluxblox.user.id}/stats"
        headers = {"Authorization": TOPGG_KEY}
        first = True

        for shard_id in SHARD_RANGE:
            payload = {
                "server_count": first and len(Fluxblox.guilds) or 0,
                "shard_count": SHARD_COUNT,
                "shard_id": shard_id
            }

            first = False

            async with aiohttp.ClientSession() as session:
                try:
                    await session.post(url, data=payload, headers=headers)
                except Exception:
                    Fluxblox.log("Failed to post TOP.GG stats")

    async def post_dbl(self):
        url = f"{DBL_API}/bots/{Fluxblox.user.id}/stats"
        headers = {"Authorization": DBL_KEY}
        first = True

        for shard_id in SHARD_RANGE:
            payload = {
                "guilds": first and len(Fluxblox.guilds) or 0,
                "shard_id": shard_id
            }

            first = False

            async with aiohttp.ClientSession() as session:
                try:
                    await session.post(url, data=payload, headers=headers)
                except Exception:
                    Fluxblox.log("Failed to post DBL stats")


    async def post_stats(self):
        if RELEASE == "MAIN":
            await self.post_topgg()
            await self.post_dbl()
