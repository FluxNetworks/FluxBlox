from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
import discord
from resources.exceptions import (Message, UserNotVerified, Error, RobloxNotFound, FluxbloxBypass, # pylint: disable=import-error, no-name-in-module
                                 Blacklisted, PermissionError, CancelCommand) # pylint: disable=import-error, no-name-in-module
from resources.constants import GREEN_COLOR # pylint: disable=import-error, no-name-in-module

get_user, get_nickname, get_roblox_id, parse_accounts, format_update_embed, guild_obligations, get_binds_explanation_button, send_account_confirmation = Fluxblox.get_module("roblox", attrs=["get_user", "get_nickname", "get_roblox_id", "parse_accounts", "format_update_embed", "guild_obligations", "get_binds_explanation_button", "send_account_confirmation"])
post_event = Fluxblox.get_module("utils", attrs=["post_event"])
set_guild_value = Fluxblox.get_module("cache", attrs=["set_guild_value"])
get_verify_link = Fluxblox.get_module("robloxnew.verifym", attrs=["get_verify_link"], name_override="verifym")
has_premium = Fluxblox.get_module("premium", attrs=["has_premium"])



class GetRoleCommand(Fluxblox.Module):
    """link your Roblox account to your Discord account and get your server roles"""

    def __init__(self):
        self.examples = ["add", "unlink", "view", "blox_link"]
        self.category = "Account"
        self.cooldown = 5
        self.dm_allowed = True
        self.slash_enabled = True
        self.slash_defer = True

    @staticmethod
    async def validate_username(message, content):
        try:
            roblox_id, username = await get_roblox_id(content)
        except RobloxNotFound:
            return None, "There was no Roblox account found with that username. Please try again."

        return username

    @Fluxblox.flags
    async def __main__(self, CommandArgs):
        guild = CommandArgs.guild
        author = CommandArgs.author
        response = CommandArgs.response

        try:
            if not guild:
                await response.info("You must run this in a server to get your roles.")
                raise UserNotVerified()

            roblox_account = (await get_user(user=author))[0]

            await send_account_confirmation(author, roblox_account, guild, response)

            if CommandArgs.command_name in ("getrole", "getroles"):
                CommandArgs.string_args = []

            old_nickname = author.display_name

            added, removed, nickname, errors, warnings, roblox_user, bind_explanations = await guild_obligations(
                CommandArgs.author,
                join                 = True,
                roblox_user          = roblox_account,
                guild                = guild,
                roles                = True,
                nickname             = True,
                cache                = False,
                response             = response,
                dm                   = False,
                exceptions           = ("FluxbloxBypass", "Blacklisted", "UserNotVerified", "PermissionError", "RobloxDown", "RobloxAPIError")
            )

        except FluxbloxBypass:
            raise Message("Since you have the `Fluxblox Bypass` role, I was unable to update your roles/nickname.", type="info")

        except Blacklisted as b:
            await response.send(b.message, hidden=True)

            raise CancelCommand()

        except UserNotVerified:
            verify_link = await get_verify_link(guild)

            binds_explanation_button = await get_binds_explanation_button({
                "success": [["unverified role", None, None, "You are not verified on Fluxblox.", []]],
                "failure": []
            })

            view = discord.ui.View()
            view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Verify with Fluxblox", url=verify_link, emoji="🔗"))
            view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Stuck? See a Tutorial", emoji="❔",
                                                 url="https://www.youtube.com/watch?v=mSbD91Zug5k&list=PLz7SOP-guESE1V6ywCCLc1IQWiLURSvBE&index=1"))

            view.add_item(item=binds_explanation_button)



            await CommandArgs.response.send("To verify with Fluxblox, click the link below.", mention_author=True, view=view)


        except PermissionError as e:
            raise Error(e.message)

        else:
            welcome_message, card, embed, view = await format_update_embed(
                roblox_user,
                author,
                guild=guild,
                added=added, removed=removed, errors=errors, warnings=warnings, nickname=nickname if old_nickname != nickname else None,
                bind_explanations=bind_explanations
            )

            message = await response.send(welcome_message, files=[card.front_card_file] if card else None, view=card.view if card else view, embed=embed, mention_author=True)

            if card:
                card.response = response
                card.message = message
                card.view.message = message

            await post_event(guild, "verification", f"{author.mention} ({author.id}) has **verified** as `{roblox_user.username}`.", GREEN_COLOR)
