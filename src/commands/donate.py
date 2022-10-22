from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from resources.constants import LIMITS # pylint: disable=import-error, no-name-in-module
import discord

PREMIUM_PERKS = "\n".join([
    f"- More role bindings allowed (from {LIMITS['BINDS']['FREE']} to {LIMITS['BINDS']['PREMIUM']}).",
    "Able to verify/update all members in your server (`/verifyall`).",
    "Able to add a verification button to your `/verifychannel` and customize the text."
    # f"- `persistRoles:` update users as they type once every 2 hours",
    f"- Access to the `Pro` version of Fluxblox - a bot in less servers, so downtime is very minimal.",
    #  "- Set an age limit that checks the person's Roblox account age. (`/settings change agelimit`).",
     "- Customize the name of Magic Roles.",
     "- No cooldown on some commands.",
     "- More restrictions (`/restrict`) " + f"allowed (from {LIMITS['RESTRICTIONS']['FREE']} to {LIMITS['RESTRICTIONS']['PREMIUM']}).",
    #  "- More groups allowed to be added to your Group-Lock (`/grouplock`).",
    "- And more!"
])


@Fluxblox.command
class DonateCommand(Fluxblox.Module):
    """learn how to receive Fluxblox Premium"""

    def __init__(self):
        self.aliases = ["premium"]
        self.dm_allowed = True
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        guild    = CommandArgs.guild

        embed = discord.Embed(title="Fluxblox Premium")
        embed.description = "Premium purchases help support Fluxblox!"

        embed.add_field(name="Server Premium", value="Unlocks premium commands, lessens restrictions, no ads for your server verification page, and more for your server.", inline=False)
        #embed.add_field(name="User Premium", value="Lessens restrictions, no cooldowns on commands, unlocks a special background for your /getinfo profile. This does NOT grant you Server Premium.", inline=False)

        view = discord.ui.View()
        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Click for Server Premium", url=f"https://blox.link/dashboard/guilds/{guild.id}/premium" if guild else "https://blox.link/"))
        #view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Click for User Premium", url="https://www.patreon.com/join/Fluxblox?"))

        await response.send(embed=embed, view=view)
