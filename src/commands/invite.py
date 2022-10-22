from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
import discord


@Fluxblox.command
class InviteCommand(Fluxblox.Module):
    """invite the bot to your server"""

    def __init__(self):
        self.dm_allowed    = True
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response

        embed = discord.Embed(title="Invite Fluxblox")
        embed.description = "To add Fluxblox to your server, click the link below."

        embed.add_field(name="Frequently Asked Questions", value="1.) I don't see my server when I try to invite the bot!\n" \
                                                                f"> There are 2 possibilities:\n> a.) you don't have the `Manage Server` " \
                                                                "role permission\n> b.) you aren't logged on the correct account; " \
                                                                "go to <https://discord.com> and log out.")


        embed.set_footer(text="Thanks for choosing Fluxblox!", icon_url=Fluxblox.user.avatar.url)

        view = discord.ui.View()
        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Invite Fluxblox", url="https://blox.link/invite"))
        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Support Server",  url="https://blox.link/support"))

        await response.send(embed=embed, view=view)
