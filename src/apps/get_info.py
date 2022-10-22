from resources.structures import Fluxblox, Card # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.exceptions import Error, RobloxNotFound, RobloxAPIError, Message, UserNotVerified # pylint: disable=import-error, no-name-in-module, no-name-in-module

get_user, get_accounts = Fluxblox.get_module("robloxnew.users", attrs=["get_user", "get_accounts"], name_override="users")


@Fluxblox.extension
class GetInfoExtension(Fluxblox.Module):
    """retrieve the Roblox information of a user"""

    def __init__(self):
        self.type = 2
        self.name = "Get Roblox Info"
        self.slash_defer = True
        self.slash_ephemeral = True
        self.premium_bypass_channel_perms = True

    async def __main__(self, ExtensionArgs):
        user   = ExtensionArgs.resolved
        guild  = ExtensionArgs.guild
        author = ExtensionArgs.author

        response = ExtensionArgs.response

        if user.bot:
            raise Error("Bots cannot have Roblox accounts!", hidden=True)

        try:
            roblox_user, _  = await get_user(user=user, guild=guild, cache=True, includes=True)
        except RobloxNotFound:
            raise Error("This Roblox account doesn't exist.")
        except RobloxAPIError:
            raise Error("The Roblox API appears to be down so I was unable to retrieve the information. Please try again later.")
        except UserNotVerified:
            raise Error("This user is not linked to Fluxblox!")
        else:
            author_accounts = await get_accounts(author)

            card = Card(user, author, author_accounts, roblox_user, "getinfo", guild, from_interaction=True)
            await card()

            card.response = response

            message = await response.send(files=[card.front_card_file], view=card.view)

            card.message = message
            card.view.message = message
