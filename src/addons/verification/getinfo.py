from resources.structures import Fluxblox, Card # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.exceptions import Error, RobloxNotFound, RobloxAPIError, Message, UserNotVerified # pylint: disable=import-error, no-name-in-module, no-name-in-module
import re

get_user, get_accounts = Fluxblox.get_module("robloxnew.users", attrs=["get_user", "get_accounts"], name_override="users")



class GetInfoCommand(Fluxblox.Module):
    """retrieve the Roblox information of a user"""

    def __init__(self):
        self.arguments = [
            {
                "prompt": "Please enter a Roblox username or Roblox ID.",
                "name": "roblox_name",
                "auto_complete": self.auto_complete_roblox_user,
                "optional": True
            },
          {
                "prompt": "Please specify a Discord user.",
                "name": "discord_user",
                "type": "user",
                "optional": True
            }
        ]
        self.cooldown = 5
        self.dm_allowed = True
        self.slash_enabled = True
        self.slash_defer = True
        self.slash_only = True
        self.aliases = ["robloxsearch", "rs", "whois"] # FIXME

        self.autocomplete_regex = re.compile("roblox-id-(.*)")

    async def auto_complete_roblox_user(self, interaction, command_args, focused_option):
        if not focused_option:
            return []

        try:
            if focused_option.isdigit():
                roblox_user = (await get_user(roblox_id=focused_option))[0]
            else:
                roblox_user = (await get_user(roblox_name=focused_option))[0]

        except (RobloxNotFound, RobloxAPIError):
            return []

        return [[f"{roblox_user.name} ({roblox_user.id})", f"roblox-id-{roblox_user.id}"]]


    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        guild = CommandArgs.guild
        author = CommandArgs.author

        roblox_info  = CommandArgs.parsed_args["roblox_name"]
        discord_user = CommandArgs.parsed_args["discord_user"]

        roblox_id = roblox_name = None

        if roblox_info and discord_user:
            raise Message("Please only specify a Roblox username OR a Discord user!", type="silly")

        elif not (roblox_info or discord_user):
            discord_user = CommandArgs.author

        if roblox_info:
            roblox_id = self.autocomplete_regex.search(roblox_info)

            if not roblox_id:
                roblox_name = roblox_info
            else:
                roblox_id = roblox_id.group(1)

        try:
            roblox_user, _  = await get_user(user=discord_user, roblox_id=roblox_id, roblox_name=roblox_name, guild=guild, cache=True, includes=True)
        except RobloxNotFound:
            raise Error("This Roblox account doesn't exist.")
        except RobloxAPIError:
            raise Error("The Roblox API appears to be down so I was unable to retrieve the information. Please try again later.")
        except UserNotVerified:
            raise Error("This user is not linked to Fluxblox!")
        else:
            author_accounts = await get_accounts(author)

            card = Card(discord_user or author, author, author_accounts, roblox_user, "getinfo", guild, from_interaction=True)
            await card()

            card.response = response

            message = await response.send(files=[card.front_card_file], view=card.view)

            card.message = message
            card.view.message = message
