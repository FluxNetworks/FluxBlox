from ..structures import Fluxblox, DonatorProfile # pylint: disable=import-error, no-name-in-module
from discord import Object
import discord
import datetime

from time import time



fetch = Fluxblox.get_module("utils", attrs="fetch")
get_db_value, set_db_value, get_user_value, set_user_value, cache_get, cache_set = Fluxblox.get_module("cache", attrs=["get_db_value", "set_db_value", "get_user_value", "set_user_value", "get", "set"])




class OldPremiumView(discord.ui.View):
    @discord.ui.button(label="Suppress Warnings", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild  = interaction.guild
        user = interaction.user

        # check if user has manage user
        if user.resolved_permissions.administrator or user.resolved_permissions.manage_guild:
            datetime_now = datetime.datetime.now()
            await set_db_value("guilds", guild, oldPremiumWarningsSuppressed=datetime_now.timestamp())
            await interaction.response.send_message("All warnings were suppressed for 2 weeks.", ephemeral=True)
        else:
            await interaction.response.send_message("You do not have permission to suppress warnings.", ephemeral=True)

        self.stop()


@Fluxblox.module
class Premium(Fluxblox.Module):
    def __init__(self):
        self.patrons = {}

        Fluxblox.loop.create_task(self.update_patrons())

    async def update_patrons(self):
        cursor = self.db.patreon.find({})

        while await cursor.fetch_next:
            patron = cursor.next_object()
            self.patrons[patron["_id"]] = True

    async def has_premium(self, guild=None, user=None):
        premium_data = await get_db_value("guilds" if guild else "users", guild or user, "premium") or {}
        tier = None
        term = None
        user_facing_tier = None

        if premium_data and premium_data.get("active"):
            if guild:
                try:
                    tier, term = premium_data["type"].split("/")

                    if tier == "basic":
                        user_facing_tier = "Basic Premium"
                    elif tier == "pro":
                        user_facing_tier = "Pro"
                except ValueError:
                    user_facing_tier = premium_data["type"]

            else:
                user_facing_tier = "User Premium"
                tier = "premium"
                term = None

            features = {"premium"}

            if tier == "pro" or premium_data.get("patreon") or "pro" in user_facing_tier.lower():
                features.add("pro")

            return DonatorProfile(
                user=user,
                guild=guild,
                typex="chargebee",
                tier=tier,
                term=term,
                user_facing_tier=user_facing_tier,
                features=features
            )

        else:
            # check patreon and selly
            return await self.check_old_premium(guild=guild, user=user)

    async def check_old_premium(self, guild=None, user=None):
        if not user:
            user = Object(guild.owner_id)

        prem_data = await get_user_value(user, "premium") or {}

        if prem_data.get("transferFrom"):
            user = Object(int(prem_data["transferFrom"]))

        return await self.has_patreon_premium(user) or await self.has_selly_premium(user) or DonatorProfile(user=user)

    async def has_selly_premium(self, user):
        prem_data = await get_user_value(user, "premium") or {}

        expiry = prem_data.get("expiry", 1)
        pro_expiry = prem_data.get("pro", 1)

        t = time()
        is_p = expiry == 0 or expiry > t
        #days_premium = expiry != 0 and expiry > t and ceil((expiry - t)/86400) or 0

        pro_access = pro_expiry == 0 or pro_expiry > t

        features = {"premium"}

        if pro_access:
            features.add("pro")

        if is_p:
            return DonatorProfile(
                user=user,
                typex="key",
                features=features,
                user_facing_tier="Basic Premium",
                old_premium=True
            )

    async def has_patreon_premium(self, user):
        if self.patrons.get(str(user.id)):
            return DonatorProfile(
                user=user,
                typex="patreon",
                features={"premium", "pro"},
                user_facing_tier="Basic",
                old_premium=True
            )

    async def add_features(self, user, features, *, days=-1):
        user_data_premium = await get_user_value(user, "premium") or {}
        prem_expiry = user_data_premium.get("expiry", 1)

        if days != -1 and days != 0:
            t = time()

            if prem_expiry and prem_expiry > t:
                # premium is still active; add time to it
                days = (days * 86400) + prem_expiry
            else:
                # premium expired
                days = (days * 86400) + t

        elif days == -1:
            days = prem_expiry

        elif days == "-":
            days = 1

        if "pro" in features:
            user_data_premium["pro"] = days # TODO: convert to -1

        if "premium" in features:
            user_data_premium["expiry"] = days # TODO: convert to -1

        if "-" in features:
            if "premium" in features:
                user_data_premium["expiry"] = 1

            if "pro" in features:
                user_data_premium["pro"] = 1

            if len(features) == 1:
                user_data_premium["expiry"] = 1
                user_data_premium["pro"] = 1

        await set_user_value(user, premium=user_data_premium)


    async def get_features(self, user=None, guild=None, cache=True, cache_as_guild=True, rec=True, premium_data=None, partner_check=True):
        # user = user or guild.owner
        # profile = DonatorProfile(user=user)

        # if cache:
        #     if guild and cache_as_guild:
        #         guild_premium_cache = await cache_get(f"premium_cache:{guild.id}")

        #         if guild_premium_cache:
        #             return guild_premium_cache[0], guild_premium_cache[1]
        #     else:
        #         premium_cache = await cache_get(f"premium_cache:{user.id}")

        #         if premium_cache:
        #             return premium_cache[0], premium_cache[1]

        # premium_data = premium_data or await get_user_value(user, "premium") or {}

        # if rec:
        #     if premium_data.get("transferTo"):
        #         if cache:
        #             if guild and cache_as_guild:
        #                 await cache_set(f"premium_cache:{guild.id}", (profile, premium_data["transferTo"]))
        #             else:
        #                 await cache_set(f"premium_cache:{user.id}", (profile, premium_data["transferTo"]))

        #         return profile, premium_data["transferTo"]

        #     elif premium_data.get("transferFrom"):
        #         transfer_from = premium_data["transferFrom"]
        #         transferee_premium, _ = await self.get_features(Object(id=transfer_from), premium_data=await get_user_value(transfer_from, "premium"), rec=False, cache=False, partner_check=False)

        #         if transferee_premium.features.get("premium"):
        #             if cache:
        #                 if guild and cache_as_guild:
        #                     await cache_set(f"premium_cache:{guild.id}", (transferee_premium, _))
        #                 else:
        #                     await cache_set(f"premium_cache:{user.id}", (transferee_premium, _))

        #             return transferee_premium, _

        # data_patreon = await self.has_patreon_premium(user, premium_data)

        # if data_patreon:
        #     profile.active = True
        #     profile.type = "patreon"
        #     profile.add_features("premium", "pro")
        # else:
        #     data_selly = await self.has_selly_premium(user, premium_data)

        #     if data_selly["premium"]:
        #         profile.add_features("premium")
        #         profile.type = "selly"

        #     if data_selly["pro_access"]:
        #         profile.add_features("pro")

        # if guild and partner_check:
        #     partners_cache = await cache_get(f"partners:guilds:{guild.id}", primitives=True, redis_hash=True, redis_hash_exists=True)

        #     if partners_cache:
        #         profile.add_features("premium")

        # if cache:
        #     if guild and cache_as_guild:
        #         await cache_set(f"premium_cache:{guild.id}", (profile, None))
        #     else:
        #         await cache_set(f"premium_cache:{user.id}", (profile, None))

        # return profile, None

        return DonatorProfile(user=user), None
