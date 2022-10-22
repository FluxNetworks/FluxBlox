from ..structures import Fluxblox # pylint: disable=import-error, no-name-in-module
from ..exceptions import Blacklisted # pylint: disable=import-error, no-name-in-module
import json
import logging

cache_get, get_guild_value = Fluxblox.get_module("cache", attrs=["get", "get_guild_value"])


@Fluxblox.module
class Blacklist(Fluxblox.Module):
    def __init__(self):
        self.blacklist = {
            "users": {},
            "guilds": {},
            "robloxAccounts": {},
            "roles": {}
        }

    async def __setup__(self):
        try:
            with open("src/data/blacklist.json", "r+") as f:
                blacklist_json = json.load(f)

                for user_id, user_data in blacklist_json["users"].items():
                    reason = user_data.get("reason") or True

                    self.blacklist["users"][user_id] = reason

                    for roblox_id in user_data.get("robloxAccounts", []):
                        self.blacklist["robloxAccounts"][roblox_id] = reason

                    for guild_id in user_data.get("guilds", []):
                        self.blacklist["guilds"][guild_id] = reason

                for guild_id, reason in blacklist_json["guilds"].items():
                    self.blacklist["guilds"][guild_id] = reason

        except FileNotFoundError:
            logging.error("Blacklist file not found.")

    async def check_restrictions(self, typex, *ids, guild=None, roblox_user=None):

        # server restrictions
        if guild:
            restrictions = await get_guild_value(guild, "restrictions")

            if restrictions:
                for idx in ids:
                    idx = str(idx)
                    restriction = restrictions.get(typex, {}).get(idx, {})

                    if restriction:
                        reason = restriction.get("reason")

                        if reason:
                            if reason.endswith("."):
                                reason = reason[:-1]

                            raise Blacklisted(f"This server has prevented you from using Fluxblox for: `{reason}`.", guild_restriction=True)

                        raise Blacklisted("This server has prevented you from using Fluxblox. This is NOT a Fluxblox blacklist.", guild_restriction=True)

                    if roblox_user:
                        for restricted_group_id, restricted_group in restrictions.get("groups", {}).items():
                            group = roblox_user.groups.get(restricted_group_id)

                            if group:
                                reason = restricted_group.get("reason")

                                if reason:
                                    if reason.endswith("."):
                                        reason = reason[:-1]

                                    raise Blacklisted(f"This server has prevented your group `{group.name}` from verifying for: `{reason}`. This is NOT a Fluxblox blacklist.", guild_restriction=True)

                                raise Blacklisted(f"This server has prevented your group `{group.name}` from verifying. This is NOT a Fluxblox blacklist.", guild_restriction=True)

        # Fluxblox-wide restrictions
        for idx in ids:
            idx = str(idx)
            global_restriction = self.blacklist[typex].get(idx)

            if global_restriction:
                if isinstance(global_restriction, str):
                    if typex == "guilds":
                        raise Blacklisted(f"This server is restricted from using Fluxblox due to a policy violation: `{global_restriction}`")

                    raise Blacklisted(f"You are restricted from using Fluxblox due to a policy violation: `{global_restriction}`.")
                else:
                    if typex == "guilds":
                        raise Blacklisted("This server is restricted from using Fluxblox due to a policy violation.")

                    raise Blacklisted("You are restricted from using Fluxblox due to a policy violation.")
