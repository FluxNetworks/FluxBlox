from ..structures import Fluxblox, Response # pylint: disable=import-error, no-name-in-module
from ..constants import DEFAULTS # pylint: disable=import-error, no-name-in-module
from ..exceptions import CancelCommand, RobloxDown, Blacklisted, UserNotVerified, PermissionError, Error # pylint: disable=import-error, no-name-in-module
import discord

get_guild_value = Fluxblox.get_module("cache", attrs=["get_guild_value"])
guild_obligations, send_account_confirmation, get_user, mask_unverified = Fluxblox.get_module("roblox", attrs=["guild_obligations", "send_account_confirmation", "get_user", "mask_unverified"])


@Fluxblox.module
class MemberUpdateEvent(Fluxblox.Module):
    def __init__(self):
        pass

    async def __setup__(self):

        @Fluxblox.event
        async def on_member_update(before, after):
            guild = before.guild

            if guild.verification_level == discord.VerificationLevel.highest:
                return

            if not before.bot and (before.pending and not after.pending) and "COMMUNITY" in guild.features:
                options = await get_guild_value(guild, ["autoRoles", DEFAULTS.get("autoRoles")], ["autoVerification", DEFAULTS.get("autoVerification")], "highTrafficServer")

                auto_roles = options.get("autoRoles")
                auto_verification = options.get("autoVerification")
                high_traffic_server = options.get("highTrafficServer")

                if high_traffic_server:
                    return

                if auto_verification or auto_roles:
                    try:
                        roblox_user = (await get_user(user=after))[0]
                    except UserNotVerified:
                        roblox_user = None
                    else:
                        try:
                            await mask_unverified(guild, after) # verified users will be treated as unverified until they confirm
                        except (PermissionError, Error, CancelCommand):
                            return

                    response = Response(None, after, after, guild)

                    try:
                        await send_account_confirmation(after, roblox_user, guild, response)
                        await guild_obligations(after, guild, cache=False, join=True, dm=True, event=True, exceptions=("RobloxDown", "Blacklisted"))
                    except CancelCommand:
                        pass
                    except RobloxDown:
                        try:
                            await after.send("Roblox appears to be down, so I was unable to retrieve your Roblox information. Please try again later.")
                        except discord.errors.Forbidden:
                            pass
                    except Blacklisted:
                        pass
