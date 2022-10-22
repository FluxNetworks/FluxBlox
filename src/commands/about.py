from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from discord import Embed


@Fluxblox.command
class AboutCommand(Fluxblox.Module):
    """learn about Fluxblox!"""

    def __init__(self):
        self.aliases = ["fluxblox"]
        self.dm_allowed    = True
        self.slash_enabled = True
        self.slash_only = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        locale   = CommandArgs.locale

        embed = Embed(title=locale("commands.about.title"))

        embed.add_field(name=locale("commands.about.embed.title"), value=f"**{locale('commands.about.embed.field_1.line_1')}**\n{locale('commands.about.embed.field_1.line_2')}"
                                                                         f"\n\n{locale('commands.about.embed.field_1.line_3')}", inline=False)


        embed.add_field(name=locale("commands.about.embed.field_2.title"), value=f"[{locale('commands.about.embed.field_2.line_1')}](https://blox.link/support)",
                        inline=False)

        embed.set_thumbnail(url=Fluxblox.user.avatar.url)


        await response.send(embed=embed)
