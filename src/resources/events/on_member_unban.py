from ..structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from ..exceptions import UserNotVerified # pylint: disable=import-error, no-name-in-module
from ..constants import DEFAULTS, RED_COLOR # pylint: disable=import-error, no-name-in-module
from discord.errors import NotFound, Forbidden, HTTPException
from discord import Object

get_guild_value, get_db_value = Fluxblox.get_module("cache", attrs=["get_guild_value", "get_db_value"])
has_premium = Fluxblox.get_module("premium", attrs=["has_premium"])
get_user = Fluxblox.get_module("roblox", attrs=["get_user"])
post_event = Fluxblox.get_module("utils", attrs=["post_event"])

@Fluxblox.module
class MemberUnBanEvent(Fluxblox.Module):
    def __init__(self):
        pass

    async def __setup__(self):

        @Fluxblox.event
        async def on_member_unban(guild, user):
            if self.redis:
                donator_profile = await has_premium(guild=guild)
                unban_related_accounts = await get_guild_value(guild, ["unbanRelatedAccounts", DEFAULTS.get("unbanRelatedAccounts")])

                if "premium" in donator_profile.features:
                    if unban_related_accounts:
                        try:
                            account, accounts, _ = await get_user(user=user, guild=guild)
                        except UserNotVerified:
                            pass
                        else:
                            accounts = set(accounts)

                            if account: #FIXME: temp until primary accounts are saved to the accounts array
                                accounts.add(account.id)

                            for roblox_id in accounts:
                                discord_ids = await get_db_value("roblox_accounts", roblox_id, "discordIDs") or []

                                for discord_id in discord_ids:
                                    discord_id = int(discord_id)

                                    if discord_id != user.id:
                                        try:
                                            ban_entry = await guild.fetch_ban(Object(discord_id))
                                        except (NotFound, Forbidden):
                                            pass
                                        else:
                                            try:
                                                await guild.unban(ban_entry.user, reason=f"unbanRelatedAccounts is enabled - alt of {user} ({user.id})")
                                            except (Forbidden, HTTPException):
                                                pass
                                            else:
                                                await post_event(guild, "moderation", f"{ban_entry.user.mention} is an alt of {user.mention} and has been `unbanned`.", RED_COLOR)
