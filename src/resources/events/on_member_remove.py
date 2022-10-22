from ..structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from ..exceptions import CancelCommand # pylint: disable=import-error, no-name-in-module

get_guild_value = Fluxblox.get_module("cache", attrs=["get_guild_value"])
guild_obligations = Fluxblox.get_module("roblox", attrs=["guild_obligations"])


@Fluxblox.module
class MemberRemoveEvent(Fluxblox.Module):
    def __init__(self):
        pass

    async def __setup__(self):

        @Fluxblox.event
        async def on_member_remove(member):
            try:
                await guild_obligations(member, member.guild, join=False, event=True)
            except CancelCommand:
                pass
