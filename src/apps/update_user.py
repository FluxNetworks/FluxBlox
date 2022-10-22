from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error, UserNotVerified, Message, FluxbloxBypass, CancelCommand, PermissionError, Blacklisted # pylint: disable=import-error, no-name-in-module
from config import REACTIONS # pylint: disable=no-name-in-module, import-error
import discord

guild_obligations = Fluxblox.get_module("roblox", attrs=["guild_obligations"])


@Fluxblox.extension
class UpdateUserExtension(Fluxblox.Module):
    """update a user's roles and nickname"""

    def __init__(self):
        self.type = 2
        self.name = "Update User"
        self.permissions = Fluxblox.Permissions().build("FLUXBLOX_UPDATER")
        self.slash_defer = True
        self.slash_ephemeral = True
        self.premium_bypass_channel_perms = True

    async def __main__(self, ExtensionArgs):
        user  = ExtensionArgs.resolved
        guild = ExtensionArgs.guild

        response   = ExtensionArgs.response

        if user.bot:
            raise Error("You cannot update bots!", hidden=True)

        if isinstance(user, discord.User):
            try:
                user = await guild.fetch_member(user.id)
            except discord.errors.NotFound:
                raise Error("This user isn't in your server!")

        try:
            added, removed, nickname, errors, warnings, roblox_user, _ = await guild_obligations(
                user,
                guild             = guild,
                roles             = True,
                nickname          = True,
                cache             = False,
                dm                = False,
                event             = True,
                exceptions        = ("FluxbloxBypass", "Blacklisted", "CancelCommand", "UserNotVerified", "PermissionError", "RobloxDown", "RobloxAPIError"))

            await response.send(f"{REACTIONS['DONE']} **Updated** {user.mention}", hidden=True)

        except FluxbloxBypass:
            raise Message("Since this user has the Fluxblox Bypass role, I was unable to update their roles/nickname.", type="info", hidden=True)

        except Blacklisted as b:
            if b.guild_restriction:
                await response.send(f"This user is server-restricted from using Fluxblox for: `{b.message}`. This is NOT a Fluxblox blacklist.", hidden=True)
            else:
                await response.send(f"This user is blacklisted from using Fluxblox for: `{b.message}`.", hidden=True)

            return

        except CancelCommand:
            pass

        except UserNotVerified:
            raise Error("This user is not linked to Fluxblox.", hidden=True)

        except PermissionError as e:
            raise Error(e.message, hidden=True)
