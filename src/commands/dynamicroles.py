from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from resources.constants import DEFAULTS, BROWN_COLOR # pylint: disable=import-error, no-name-in-module

post_event = Fluxblox.get_module("utils", attrs=["post_event"])
set_guild_value, get_guild_value = Fluxblox.get_module("cache", attrs=["set_guild_value", "get_guild_value"])


@Fluxblox.command
class DynamicRolesCommand(Fluxblox.Module):
    """automatically create missing group roles. by default, this is ENABLED."""

    def __init__(self):
        self.permissions = Fluxblox.Permissions().build("FLUXBLOX_MANAGER")
        self.category = "Administration"
        self.hidden = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        author = CommandArgs.author
        guild = CommandArgs.guild

        toggle = not (await get_guild_value(guild, "dynamicRoles") or DEFAULTS.get("dynamicRoles"))

        await set_guild_value(guild, dynamicRoles=toggle)

        if toggle:
            await post_event(guild, "configuration", f"{author.mention} ({author.id}) has **enabled** `dynamicRoles`.", BROWN_COLOR)
            await response.success("Successfully **enabled** Dynamic Roles!")
        else:
            await post_event(guild, "configuration", f"{author.mention} ({author.id}) has **disabled** `dynamicRoles`.", BROWN_COLOR)
            await response.success("Successfully **disabled** Dynamic Roles!")
