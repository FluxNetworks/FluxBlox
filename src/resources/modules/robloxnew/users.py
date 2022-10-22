from ...structures.Fluxblox import Fluxblox # pylint: disable=no-name-in-module, import-error
from ...constants import RBX_STAFF, RBX_STAR, FLUXBLOX_STAFF # pylint: disable=no-name-in-module, import-error
from ...exceptions import (RobloxNotFound, UserNotVerified) # pylint: disable=no-name-in-module, import-error
from .groups import Group # pylint: disable=no-name-in-module, import-error
import asyncio
from datetime import datetime
import dateutil.parser as parser
import math


API_URL = "https://api.roblox.com"
ALL_USER_API_SCOPES = ["groups", "badges"]


fetch = Fluxblox.get_module("utils", attrs=["fetch"])
cache_set, cache_get, get_user_value = Fluxblox.get_module("cache", attrs=["set", "get", "get_user_value"])
get_linked_group_ids = Fluxblox.get_module("robloxnew.binds", attrs=["get_linked_group_ids"], name_override="binds")




class RobloxUser:
    __slots__ = ("name", "id", "complete", "groups",
                 "avatar", "premium", "presence", "badges", "description",
                 "banned", "age_days", "created", "profile_link", "devforum", "display_name",
                 "group_ranks", "overlay", "flags", "headshot", "year_created",
                 "short_age_string")

    def __init__(self, name=None, id=None):
        self.name = name
        self.id = id
        self.groups = None
        self.avatar = None
        self.premium = None
        self.presence = None
        self.badges = None
        self.description = None
        self.banned = None
        self.created = None
        self.devforum = None
        self.display_name = None
        self.group_ranks = None
        self.flags = None
        self.overlay = None
        self.age_days = None
        self.year_created = None
        self.profile_link = None
        self.headshot = None
        self.short_age_string = None

        self.complete = False

    async def sync(self, includes=None, *, cache=True, no_flag_check=False):
        if includes is None:
            includes = []
        elif includes is True:
            includes = ALL_USER_API_SCOPES
            self.complete = True

        if cache:
            # remove includes if we already have the value saved
            if self.groups is not None and "groups" in includes:
                includes.remove("groups")

            if self.presence is not None and "presence" in includes:
                includes.remove("presence")

            if self.badges is not None and "badges" in includes:
                includes.remove("badges")

        includes = ",".join(includes)

        user_json_data, user_data_response = await fetch(f"https://Fluxblox-info-server-vunlj.ondigitalocean.app/roblox/info?id={self.id}&include={includes}", json=True)
        #user_json_data, user_data_response = await fetch(f"https://faas-nyc1-2ef2e6cc.doserverless.co/api/v1/web/fn-0251fcbd-1e13-4992-b488-ef68fa029b1c/default/user-info?id={self.id}&include={includes}", json=True)

        if user_data_response.status == 200:
            self.description = user_json_data.get("description", self.description)
            self.name = user_json_data.get("name", self.name)
            self.banned = user_json_data.get("isBanned", self.banned)
            #self.join_date = user_json_data.get("joinDate", self.join_date)
            self.year_created = user_json_data.get("yearCreated", self.year_created)
            self.profile_link = user_json_data.get("profileLink", self.profile_link)
            #self.presence = user_json_data.get("presence", self.presence)
            self.presence = None
            self.badges = user_json_data.get("badges", self.badges)
            self.display_name = user_json_data.get("displayName", self.display_name)
            self.created = user_json_data.get("created", self.created)

            self.parse_groups(user_json_data.get("groups"))

            if self.badges and self.groups and not no_flag_check:
                await self.parse_flags()

            self.parse_age()

            avatar = user_json_data.get("avatar")

            if avatar:
                avatar_url, avatar_response = await fetch(avatar["bustThumbnail"])

                if avatar_response.status == 200:
                    self.avatar = avatar_url.get("data", [{}])[0].get("imageUrl")

    async def get_group_ranks(self, guild):
        group_ranks = {}

        if self.groups is None:
            await self.sync(includes=["groups"])

        linked_groups = await get_linked_group_ids(guild)

        for group_id in linked_groups:
            group = self.groups.get(group_id)

            if group:
                group_ranks[group.name] = group.rank_name

        return group_ranks

    def parse_age(self):
        if (self.age_days is not None) or not self.created:
            return

        today = datetime.today()
        roblox_user_age = parser.parse(self.created).replace(tzinfo=None)
        self.age_days = (today - roblox_user_age).days

        # join_date = f"{roblox_user_age.month}/{roblox_user_age.day}/{roblox_user_age.year}"
        #roblox_data["join_date"] = join_date

        if not self.short_age_string:
            if self.age_days >= 365:
                years = math.floor(self.age_days/365)
                ending = f"yr{((years > 1 or years == 0) and 's') or ''}"
                self.short_age_string = f"{years} {ending} ago"
            else:
                ending = f"day{((self.age_days > 1 or self.age_days == 0) and 's') or ''}"
                self.short_age_string = f"{self.age_days} {ending} ago"


        #full_join_string = f"{age_string} ({join_date})"
        #roblox_data["full_join_string"] = full_join_string
        #roblox_data["age_string"] = age_string

    async def parse_flags(self):
        if self.flags is not None:
            return

        if self.badges is None or self.groups is None:
            await self.sync(includes=["badges", "groups"], cache=True, no_flag_check=True)

        if self.groups is None:
            print("error for flags", self.name, self.id)
            return

        flags = 0

        if "3587262" in self.groups and self.groups["3587262"].rank_value >= 50:
            flags = flags | FLUXBLOX_STAFF

        if "4199740" in self.groups:
            flags = flags | RBX_STAR

        if self.badges and "Administrator" in self.badges:
            flags = flags | RBX_STAFF

        self.flags = flags
        self.overlay = self.flags & RBX_STAFF or self.flags & RBX_STAFF or self.flags & RBX_STAR

    def parse_groups(self, group_json):
        if group_json is None:
            return

        self.groups = {}

        for group_data in group_json:
            group_meta = group_data.get("group")
            group_role = group_data.get("role")

            group = Group(group_meta, group_role)
            self.groups[group.id] = group


    def __str__(self):
        return f"{self.name} ({self.id})"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return self.id == getattr(other, "id", -1)


class DiscordProfile:
    __slots__ = ("id", "primary_account", "accounts", "guilds")

    def __init__(self, user_id, **kwargs):
        self.id = user_id

        self.primary_account = kwargs.get("primary_account")
        self.accounts = kwargs.get("accounts", [])
        self.guilds = kwargs.get("guilds", {})

    def __eq__(self, other):
        return self.id == getattr(other, "id", None)




@Fluxblox.module
class Users(Fluxblox.Module):
    def __init__(self):
        pass

    async def get_user(self, user=None, *, roblox_name=None, roblox_id=None, includes=None, guild=None, cache=True):
        roblox_user = None
        roblox_accounts = []
        discord_profile = None

        if user:
            if cache:
                discord_profile = await cache_get(f"discord_profiles_v2:{user.id}")

                if discord_profile:
                    roblox_user = discord_profile.guilds.get(guild.id) if guild else discord_profile.primary_account

                    if roblox_user:
                        await roblox_user.sync(includes, cache=cache)

                        return roblox_user, discord_profile.accounts

            roblox_id, primary_account, roblox_accounts = await self.get_user_chosen_account(user, guild)

            if not discord_profile:
                discord_profile = DiscordProfile(str(user.id))

                if primary_account:
                    discord_profile.primary_account = RobloxUser(id=primary_account)

                    if roblox_user != primary_account:
                        await discord_profile.primary_account.sync(includes, cache=cache)

                discord_profile.accounts = roblox_accounts

            if not roblox_id:
                raise UserNotVerified

        else:
            if not roblox_id:
                roblox_id = (await self.get_roblox_id(roblox_name))[0]

            if cache:
                roblox_user = await cache_get(f"roblox_users_v2:{id}")

        roblox_user = roblox_user or RobloxUser(name=roblox_name, id=roblox_id)

        await roblox_user.sync(includes, cache=cache)

        if cache:
            if roblox_user:
                await cache_set(f"roblox_users_v2:{roblox_id}", roblox_user)

            if discord_profile:

                if guild:
                    discord_profile.guilds[guild.id] = roblox_user

                await cache_set(f"discord_profiles_v2:{user.id}", discord_profile)

        return roblox_user, roblox_accounts

    async def get_user_chosen_account(self, user, guild):
        options = await get_user_value(user, "robloxAccounts", "robloxID") or {}

        accounts = options.get("robloxAccounts", {}).get("accounts", [])
        guilds = options.get("robloxAccounts", {}).get("guilds", {})
        primary_account = options.get("robloxID")

        roblox_account = guild and guilds.get(str(guild.id)) or primary_account

        return roblox_account, primary_account, accounts

    @staticmethod
    async def get_roblox_id(username):
        username_lower = username.lower()
        roblox_cached_data = await cache_get(f"usernames_to_ids:{username_lower}")

        if roblox_cached_data:
            return roblox_cached_data

        json_data, response = await fetch(f"{API_URL}/users/get-by-username/?username={username}", json=True, raise_on_failure=True)

        if json_data.get("success") is False:
            raise RobloxNotFound

        correct_username, roblox_id = json_data.get("Username"), str(json_data.get("Id"))

        data = (roblox_id, correct_username)

        if correct_username:
            await cache_set(f"usernames_to_ids:{username_lower}", data)

        return data

    @staticmethod
    async def get_roblox_username(roblox_id):
        roblox_cached_data = await cache_get(f"ids_to_username:{roblox_id}")

        if roblox_cached_data:
            return roblox_cached_data

        json_data, response = await fetch(f"{API_URL}/users/{roblox_id}", json=True, raise_on_failure=True)

        if json_data.get("success") is False:
            raise RobloxNotFound

        correct_username, roblox_id = json_data.get("Username"), str(json_data.get("Id"))

        if correct_username:
            await cache_set(f"ids_to_username:{roblox_id}", correct_username)


        return roblox_id, correct_username

    async def get_accounts(self, user, parse_accounts=False):
        ids = (await get_user_value(user, ["robloxAccounts", {}])).get("accounts", [])

        accounts = {}
        tasks = []

        for roblox_id in ids:
            roblox_user = RobloxUser(id=roblox_id)
            accounts[roblox_user.id] = roblox_user

            if parse_accounts:
                tasks.append(roblox_user.sync(cache=True))

        if parse_accounts:
            await asyncio.wait(tasks)

        return accounts

