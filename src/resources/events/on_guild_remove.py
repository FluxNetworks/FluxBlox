from ..structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from resources.constants import RELEASE # pylint: disable=import-error, no-name-in-module, no-name-in-module


set_guild_value = Fluxblox.get_module("cache", attrs=["set_guild_value"])



@Fluxblox.module
class GuildRemoveEvent(Fluxblox.Module):
    def __init__(self):
        pass

    async def __setup__(self):

        @Fluxblox.event
        async def on_guild_remove(guild):
            if RELEASE == "PRO":
                await set_guild_value(guild, proBot=False)
