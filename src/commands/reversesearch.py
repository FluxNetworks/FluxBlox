from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error, RobloxNotFound # pylint: disable=import-error, no-name-in-module
from discord import Embed
from discord.errors import NotFound

get_user = Fluxblox.get_module("roblox", attrs=["get_user"])
get_db_value = Fluxblox.get_module("cache", attrs=["get_db_value"])


@Fluxblox.command
class ReverseSearchCommand(Fluxblox.Module):
    """find Discord IDs in your server that are linked to a certain Roblox ID"""

    def __init__(self):
        self.examples = ["1", "569422833", "blox_link"]
        self.arguments = [{
            "prompt": "Please specify either a username or Roblox ID. If the person's name is all numbers, "
                      "then attach a `--username` flag to this command. Example: `!getinfo 1234 --username` will "
                      "search for a user with a Roblox username of '1234' instead of a Roblox ID.",
            "slash_desc": "Please specify either a Roblox username or ID.",
            "name": "target"
        }]
        self.category = "Administration"
        self.permissions = Fluxblox.Permissions().build("FLUXBLOX_MANAGER")
        self.aliases = ["reverse-search"]
        self.slash_enabled = True

    @Fluxblox.flags
    async def __main__(self, CommandArgs):
        guild = CommandArgs.guild
        target = CommandArgs.parsed_args["target"]
        flags = CommandArgs.flags
        response = CommandArgs.response

        username = ID = False

        if "username" in flags:
            username = True
        elif target.isdigit():
            ID = True
        else:
            username = True

        #async with response.loading():
        try:
            account = (await get_user(username=username and target, roblox_id=ID and target))[0]
        except RobloxNotFound:
            raise Error("This Roblox account doesn't exist.")
        else:
            roblox_id = account.id
            discord_ids = await get_db_value("roblox_accounts", roblox_id, "discordIDs") or []
            results = []

            if discord_ids:
                for discord_id in discord_ids:
                    try:
                        user = await guild.fetch_member(int(discord_id))
                    except NotFound:
                        pass
                    else:
                        results.append(f"{user.mention} ({user.id})")

            embed = Embed(title=f"Reverse Search for {account.username}")
            embed.set_thumbnail(url=account.avatar)

            if results:
                embed.description = "\n".join(results)
            else:
                embed.description = "No results found."

            await response.send(embed=embed)
