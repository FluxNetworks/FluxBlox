from ..structures.Fluxblox import Fluxblox # pylint: disable=no-name-in-module, import-error
from ..structures.Card import Card # pylint: disable=no-name-in-module, import-error
from ..exceptions import (BadUsage, RobloxAPIError, Error, CancelCommand, UserNotVerified,# pylint: disable=no-name-in-module, import-error
                           RobloxNotFound, PermissionError, FluxbloxBypass, RobloxDown, Blacklisted)
from typing import Tuple
import discord
from datetime import datetime
from config import REACTIONS # pylint: disable=import-error, no-name-in-module
from ..constants import (FLUXBLOX_STAFF, RELEASE, DEFAULTS,SERVER_INVITE, GREEN_COLOR, # pylint: disable=import-error, no-name-in-module
                         RED_COLOR, VERIFY_URL, IGNORED_SERVERS, CLUSTER_ID, ORANGE_COLOR) # pylint: disable=import-error, no-name-in-module
import json
import re
import asyncio
import dateutil.parser as parser
import math
import traceback
import uuid
import async_timeout


nickname_template_regex = re.compile(r"\{(.*?)\}")
any_group_nickname = re.compile(r"\{group-rank-(.*?)\}")
bracket_search = re.compile(r"\[(.*)\]")
roblox_group_regex = re.compile(r"roblox.com/groups/(\d+)/")



fetch, post_event = Fluxblox.get_module("utils", attrs=["fetch", "post_event"])
has_premium = Fluxblox.get_module("premium", attrs=["has_premium"])
cache_set, cache_get, cache_pop, get_guild_value, get_db_value, get_user_value, set_db_value, set_user_value = Fluxblox.get_module("cache", attrs=["set", "get", "pop", "get_guild_value", "get_db_value", "get_user_value", "set_db_value", "set_user_value"])
check_restrictions = Fluxblox.get_module("blacklist", attrs=["check_restrictions"])
has_magic_role = Fluxblox.get_module("extras", attrs=["has_magic_role"])


API_URL = "https://api.roblox.com"
BASE_URL = "https://www.roblox.com"
GROUP_API = "https://groups.roblox.com"
THUMBNAIL_API = "https://thumbnails.roblox.com"



@Fluxblox.module
class Roblox(Fluxblox.Module):
    def __init__(self):
        self.pending_verifications = {}
        self.pending_tasks = {}

    async def __setup__(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"ACCOUNT_CONFIRM:{CLUSTER_ID}")

        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True)

                if message:
                    self.loop.create_task(self.account_confirm_message(message))

            except self.redis.exceptions.ConnectionError:
                while True:
                    try:
                        await self.redis.ping()
                    except self.redis.exceptions.ConnectionError:
                        await asyncio.sleep(10)
                    else:
                        await pubsub.subscribe(f"ACCOUNT_CONFIRM:{CLUSTER_ID}")
                        break

    async def account_confirm_message(self, message):
        message = json.loads(str(message["data"], "utf-8"))

        data  = message["data"]
        nonce = message["nonce"]

        task = self.pending_tasks.get(nonce)

        if not task:
            return

        if not task.done():
            task.set_result(bool(data.get("confirmed")))
        else:
            self.pending_tasks.pop(nonce, None)


    async def confirm_account(self, guild_id, roblox_id):
        future = self.loop.create_future()
        nonce = str(uuid.uuid4())

        self.pending_tasks[nonce] = future

        await self.redis.set(f"account_confirm:{guild_id}:{roblox_id}", json.dumps([nonce, CLUSTER_ID]), ex=3600)

        try:
            async with async_timeout.timeout(1000):
                await future
        except asyncio.TimeoutError:
            pass

        result = self.pending_tasks[nonce].result()
        self.pending_tasks.pop(nonce, None)

        return result

    async def send_account_confirmation(self, user, roblox_account, guild, response, ephemeral=False):
        if roblox_account and not "premium" in (await has_premium(guild=guild)).features:
            roblox_accounts = await get_user_value(user, "robloxAccounts") or {"confirms": {}}
            user_confirms = roblox_accounts.get("confirms", {})

            if user_confirms.get(str(roblox_account.id)) in (True, str(guild.id)): # FIXME: old confirms, need to pop from database
                user_confirms.pop(str(roblox_account.id), None)
                roblox_accounts["confirms"] = user_confirms
                await set_user_value(user, robloxAccounts=roblox_accounts)

            if user_confirms.get(str(guild.id)) == str(roblox_account.id):
                return

            try:
                view = discord.ui.View()
                embed = discord.Embed(
                    title="Confirm Account",
                    description=f"Are you sure you want to use Roblox account **{roblox_account.username}** in this server?"

                )

                embed.colour = ORANGE_COLOR

                view.add_item(
                    item=discord.ui.Button(style=discord.ButtonStyle.link, label="Confirm Account", url=f"https://blox.link/confirm/{guild.id}/{roblox_account.id}")
                )
                view.add_item(
                    item=discord.ui.Button(style=discord.ButtonStyle.link, label="Deny Account", url=f"https://blox.link/confirm/{guild.id}/{roblox_account.id}")
                )

                confirmation_message = await response.send(embed=embed, view=view, hidden=ephemeral)

                confirmed = await self.confirm_account(guild.id, roblox_account.id)

                if not confirmed:
                    raise CancelCommand()

                embed.colour = GREEN_COLOR
                embed.description = "Thanks for confirming the account! Confirmation helps us secure verifications."
                embed.title = "Confirmed Account"

                await confirmation_message.edit(embed=embed)

                user_confirms[str(guild.id)] = str(roblox_account.id)
                roblox_accounts["confirms"] = user_confirms

                await set_user_value(user, robloxAccounts=roblox_accounts)

            except discord.errors.Forbidden:
                raise CancelCommand()

    async def mask_unverified(self, guild, member):  # only used for non-premium servers to mask a user as unverified so they can confirm prompt
        if not "premium" in (await has_premium(guild=guild)).features:
            options = await get_guild_value(guild,
                                            ["unverifiedRoleEnabled", DEFAULTS.get("unverifiedRoleEnabled")],
                                            "unverifiedRole",)

            unverify_role_enabled = options.get("unverifiedRoleEnabled")
            unverified_role_name = options.get("unverifiedRoleName") or DEFAULTS.get("unverifiedRoleName")

            unverified_role_id = int(options.get("unverifiedRole")) if options.get("unverifiedRole") else None

            unverified_role = None

            if unverify_role_enabled:
                if unverified_role_id:
                    unverified_role = discord.utils.find(lambda r: (r.id == unverified_role_id) and not r.managed, guild.roles)

                if not unverified_role:
                    unverified_role = discord.utils.find(lambda r: (r.name == unverified_role_name.strip()) and not r.managed, guild.roles)

                if not unverified_role:
                    try:
                        unverified_role = await guild.create_role(name=unverified_role_name, reason="Creating missing Unverified role")
                    except discord.errors.Forbidden:
                        raise PermissionError("I was unable to create the Unverified Role. Please "
                                            "ensure I have the `Manage Roles` permission.")
                    except discord.errors.HTTPException:
                        raise Error("Unable to create role: this server has reached the max amount of roles!")

                try:
                    await member.add_roles(unverified_role)
                except discord.errors.Forbidden:
                    raise PermissionError("I was unable to give you the Unverified role.")
                except discord.errors.NotFound:
                    raise CancelCommand()

    @staticmethod
    async def get_roblox_id(username) -> Tuple[str, str]:
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
    async def get_roblox_username(roblox_id) -> Tuple[str, str]:
        roblox_user = await cache_get(f"roblox_users:{roblox_id}")

        if roblox_user and roblox_user.verified:
            return roblox_user.id, roblox_user.username

        json_data, response = await fetch(f"{API_URL}/users/{roblox_id}", json=True, raise_on_failure=True)

        if json_data.get("success") is False:
            raise RobloxNotFound

        correct_username, roblox_id = json_data.get("Username"), str(json_data.get("Id"))

        data = (roblox_id, correct_username)

        return data

    @staticmethod
    async def validate_code(roblox_id, code):
        if RELEASE == "LOCAL":
            return True

        try:
            html_text, _ = await fetch(f"https://www.roblox.com/users/{roblox_id}/profile", raise_on_failure=True)
        except RobloxNotFound:
            raise Error("You cannot link as a banned user. Please try again with another user.")

        return code in html_text


    async def parse_accounts(self, accounts, reverse_search=False):
        parsed_accounts = {}

        for account in accounts:
            roblox_user = RobloxUser(roblox_id=account)
            await roblox_user.sync()

            if reverse_search:
                discord_ids = await get_db_value("roblox_accounts", account, "discordIDs") or []
                discord_accounts = []

                for discord_id in discord_ids:
                    try:
                        user = await Fluxblox.fetch_user(int(discord_id))
                    except discord.errors.NotFound:
                        pass
                    else:
                        discord_accounts.append(user)

                parsed_accounts[roblox_user.username] = (roblox_user, discord_accounts)

            else:
                parsed_accounts[roblox_user.username] = roblox_user

        return parsed_accounts

    @staticmethod
    async def count_binds(guild):
        all_binds = await get_guild_value(guild, ["roleBinds", {}], ["groupIDs", {}])

        role_binds = all_binds["roleBinds"]
        group_ids  = all_binds["groupIDs"]

        bind_count = 0

        for bind_category, binds in role_binds.items():
            for bind_data in binds.values():
                if bind_data:
                    if bind_category == "groups":
                        bind_count += len(bind_data.get("binds", {})) + len(bind_data.get("ranges", {}))
                    else:
                        bind_count += 1

        bind_count += len(group_ids)

        return bind_count


    async def extract_accounts(self, user, resolve_to_users=True, reverse_search=False):
        roblox_ids = {}

        options = await get_user_value(user, "robloxID", ["robloxAccounts", {}])

        primary_account = options.get("robloxID")
        if primary_account:
            roblox_ids[primary_account] = True

        for roblox_id in options.get("robloxAccounts", {}).get("accounts", []):
            roblox_ids[roblox_id] = True

        if reverse_search:
            for roblox_id in roblox_ids.keys():
                discord_ids = await get_db_value("roblox_accounts", roblox_id, "discordIDs") or []
                discord_accounts = []

                if resolve_to_users:
                    for discord_id in discord_ids:
                        try:
                            user = await Fluxblox.fetch_user(int(discord_id))
                        except discord.errors.NotFound:
                            pass
                        else:
                            discord_accounts.append(user)
                else:
                    discord_accounts = discord_ids

                roblox_ids[roblox_id] = discord_accounts

            return roblox_ids
        else:
            return list(roblox_ids.keys())


    async def verify_member(self, user, roblox, guild=None, primary_account=False, allow_reverify=True):
        user_id = str(user.id)
        guild = guild or getattr(user, "guild", None)
        guild_id = guild and str(guild.id)

        set_options = {}

        if isinstance(roblox, RobloxUser):
            roblox_id = str(roblox.id)
        else:
            roblox_id = str(roblox)

        roblox_accounts = await get_user_value(user, "robloxAccounts") or {}
        roblox_list = roblox_accounts.get("accounts", [])

        if guild:
            guild_list = roblox_accounts.get("guilds", {})
            guild_find = guild_list.get(guild_id)

            if guild_find and not allow_reverify and guild_find != roblox:
                raise Error("You already selected your account for this server! `allowReVerify` must be enabled for you to change your account.")

            guild_list[guild_id] = roblox_id
            roblox_accounts["guilds"] = guild_list


        if not roblox_id in roblox_list:
            roblox_list.append(roblox_id)
            roblox_accounts["accounts"] = roblox_list

        discord_ids = await get_db_value("roblox_accounts", roblox_id, "discordIDs") or []

        if user_id not in discord_ids:
            discord_ids.append(user_id)

            await set_db_value("roblox_accounts", roblox_id, discordIDs=discord_ids)

        if primary_account:
            set_options["robloxID"] = roblox_id

        set_options["robloxAccounts"] = roblox_accounts

        await set_user_value(user, **set_options)

        await cache_pop(f"discord_profiles:{user_id}")

    async def unverify_member(self, user, roblox):
        user_id = str(user.id)
        success = False
        set_options = {}

        if isinstance(roblox, RobloxUser):
            roblox_id = str(roblox.id)
        else:
            roblox_id = str(roblox)

        await check_restrictions("users", user.id) or await check_restrictions("robloxAccounts", roblox_id)

        options = await get_user_value(user, ["robloxAccounts", {}], "robloxID")
        roblox_accounts = options.get("robloxAccounts", {})
        roblox_list = roblox_accounts.get("accounts", [])
        guilds = roblox_accounts.get("guilds", {})

        discord_ids = await get_db_value("roblox_accounts", roblox_id, "discordIDs") or []

        if roblox_id in roblox_list:
            roblox_list.remove(roblox_id)
            roblox_accounts["accounts"] = roblox_list
            success = True

        for i,v in dict(guilds).items():
            if v == roblox_id:
                try:
                    guild = await Fluxblox.fetch_guild(int(i))
                except (discord.errors.Forbidden, discord.errors.HTTPException):
                    pass
                else:
                    try:
                        member = await guild.fetch_member(user.id)
                    except (discord.errors.Forbidden, discord.errors.NotFound):
                        pass
                    else:
                        for role in member.roles:
                            if role != guild.default_role and role.name != "Muted":
                                try:
                                    await member.remove_roles(role, reason="Unlinked")
                                except discord.errors.Forbidden:
                                    pass

                guilds.pop(i, None)

                success = True


        if options.get("robloxID") == roblox_id:
            set_options["robloxID"] = None

        roblox_accounts["guilds"] = guilds
        set_options["robloxAccounts"] = roblox_accounts

        if user_id in discord_ids:
            discord_ids.remove(user_id)

            if not discord_ids:
                #await self.r.table("robloxAccounts").get(roblox_id).delete().run()
                pass
            else:
                await set_db_value("roblox_accounts", roblox_id, discordIDs=discord_ids)


        await set_user_value(user, **set_options)

        await cache_pop(f"discord_profiles:{user_id}")

        return success


    async def get_clan_tag(self, user, guild, response, dm=False):
        clan_tags = await get_user_value(user, "clanTags") or {}

        def get_from_db():
            return clan_tags.get(str(guild.id))

        if not response:
            return get_from_db()

        # TODO: make a modal
        # clan_tag = (await response.prompt([{
        #     "prompt": "Please provide text for your Clan Tag. This will be inserted into "
        #               "your nickname.\n**Please keep your clan tag under 10 characters**, "
        #               "or it may not properly show.\nIf you want to skip this, then say `skip`.",
        #     "name": "clan_tag",
        #     "max": 32
        # }], dm=dm))["clan_tag"]

        # if clan_tag.lower() == "skip":
        #     return get_from_db()

        # clan_tags[str(guild.id)] = clan_tag
        # user_data["clanTags"] = clan_tags
        # await self.r.db("fluxblox").table("users").insert(user_data, conflict="update").run()

        clan_tag = get_from_db() # FIXME

        return clan_tag


    async def save_binds_explanations(self, bind_explanations):
        nonce = str(uuid.uuid4())

        await self.redis.set(f"binds:{nonce}", json.dumps(bind_explanations), ex=3600)

        return nonce

    async def get_binds_explanation_button(self, bind_explanations):
        if bind_explanations is not None:
            binds_token = await self.save_binds_explanations(bind_explanations)
            bind_explanation_button = discord.ui.Button(style=discord.ButtonStyle.link,
                                                        label="Expecting different roles?",
                                                        url=f"https://{'Fluxblox.dev' if RELEASE in ('LOCAL', 'CANARY') else 'blox.link'}/binds/{binds_token}")

            return bind_explanation_button

    async def format_update_embed(self, roblox_user, user, *, guild, added, removed, errors, warnings, nickname, author=None, from_interaction=True, bind_explanations=None):
        author = author or user

        welcome_message = await get_guild_value(guild, ["welcomeMessage", DEFAULTS.get("welcomeMessage")])
        welcome_message = await self.get_nickname(user, welcome_message, roblox_user=roblox_user, is_nickname=False)

        embed = None
        card  = None
        view  = discord.ui.View()

        bind_explanation_button = await self.get_binds_explanation_button(bind_explanations)

        if not (added or removed or errors or nickname):
            embed = discord.Embed(description="This user is all up-to-date; no changes were made. If this message isn't what you expected, then please contact this server's admins as they did not set up the bot or role permissions correctly.")

            if bind_explanation_button:
                view.add_item(item=bind_explanation_button)
        else:
            high_traffic_server = await get_guild_value(guild, "highTrafficServer")

            if not high_traffic_server:
                author_accounts = await self.get_accounts(author)
                card = Card(user, author, author_accounts, roblox_user, "verify", guild, extra_components=[bind_explanation_button] if bind_explanations is not None else [], extra_data={"added": added, "removed": removed, "nickname": nickname, "errors": errors, "warnings": warnings}, from_interaction=from_interaction)

                await card()
            else:
                welcome_message = "You were successfully verified!"

                if bind_explanations is not None:
                    view.add_item(item=bind_explanation_button)

        # view = discord.ui.View()
        # view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Add/Change Account", url=VERIFY_URL, emoji="🔗"))
        # view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Remove Account", emoji="🧑‍🔧", url=ACCOUNT_SETTINGS_URL))

        return welcome_message, card, embed, view

    async def get_nickname(self, user, template=None, group=None, *, guild=None, skip_roblox_check=False, response=None, is_nickname=True, roblox_user=None, dm=False):
        template = template or ""

        if template == "{disable-nicknaming}":
            return

        guild = guild or user.guild
        roblox_user = roblox_user or (not skip_roblox_check and (await self.get_user(user=user, everything=True))[0])

        if isinstance(roblox_user, tuple):
            roblox_user = roblox_user[0]

        if roblox_user:
            if not roblox_user.complete:
                await roblox_user.sync(everything=True)

            if not group:
                groups = list((await get_guild_value(guild, ["groupIDs", {}])).keys())
                group_id = groups and groups[0]

                if group_id:
                    group = roblox_user.groups.get(group_id)

            group_role = group and group.user_rank_name or "Guest"

            if await get_guild_value(guild, ["shorterNicknames", DEFAULTS.get("shorterNicknames")]):
                if group_role != "Guest":
                    brackets_match = bracket_search.search(group_role)

                    if brackets_match:
                        group_role = f"[{brackets_match.group(1)}]"

            template = template or DEFAULTS.get("nicknameTemplate") or ""

            if template == "{disable-nicknaming}":
                return

            for group_id in any_group_nickname.findall(template):
                group = roblox_user.groups.get(group_id)
                group_role_from_group = group and group.user_rank_name or "Guest"

                if await get_guild_value(guild, ["shorterNicknames", DEFAULTS.get("shorterNicknames")]):
                    if group_role_from_group != "Guest":
                        brackets_match = bracket_search.search(group_role_from_group)

                        if brackets_match:
                            group_role_from_group = f"[{brackets_match.group(1)}]"

                template = template.replace("{group-rank-"+group_id+"}", group_role_from_group)

            if "smart-name" in template:
                if roblox_user.display_name != roblox_user.username:
                    smart_name = f"{roblox_user.display_name} (@{roblox_user.username})"

                    if len(smart_name) > 32:
                        smart_name = roblox_user.username
                else:
                    smart_name = roblox_user.username
            else:
                smart_name = ""

            template = template.replace(
                "roblox-name", roblox_user.username
            ).replace(
                "display-name", roblox_user.display_name,
            ).replace(
                "smart-name", smart_name,
            ).replace(
                "roblox-id", str(roblox_user.id)
            ).replace(
                "roblox-age", str(roblox_user.age)
            ).replace(
                "roblox-join-date", roblox_user.join_date
            ).replace(
                "group-rank", group_role
            )

        else:
            if not template:
                template = await get_guild_value(guild, ["unverifiedNickname", DEFAULTS.get("unverifiedNickname")]) or ""

                if template == "{disable-nicknaming}":
                    return

        template = template.replace(
            "discord-name", user.name
        ).replace(
            "discord-nick", user.display_name
        ).replace(
            "discord-mention", user.mention
        ).replace(
            "discord-id", str(user.id)
        ).replace(
            "server-name", guild.name
        ).replace(
            "prefix", "/"
        ).replace(
            "group-url", group.url if group else ""
        ).replace(
            "group-name", group.name if group else ""
        )

        for outer_nick in nickname_template_regex.findall(template):
            nick_data = outer_nick.split(":")
            nick_fn = None
            nick_value = None

            if len(nick_data) > 1:
                nick_fn = nick_data[0]
                nick_value = nick_data[1]
            else:
                nick_value = nick_data[0]

            # nick_fn = capA
            # nick_value = roblox-name

            if nick_fn:
                if nick_fn in ("allC", "allL"):
                    if nick_fn == "allC":
                        nick_value = nick_value.upper()
                    elif nick_fn == "allL":
                        nick_value = nick_value.lower()

                    template = template.replace("{{{0}}}".format(outer_nick), nick_value)
                else:
                    template = template.replace("{{{0}}}".format(outer_nick), outer_nick) # remove {} only
            else:
                template = template.replace("{{{0}}}".format(outer_nick), nick_value)

        # clan tags are done at the end bc we may need to shorten them, and brackets are removed at the end
        clan_tag = "clan-tag" in template and (await self.get_clan_tag(user=user, guild=guild, response=response, dm=dm) or "N/A")

        if is_nickname:
            if clan_tag:
                characters_left = 32 - len(template) + 8
                clan_tag = clan_tag[:characters_left]
                template = template.replace("clan-tag", clan_tag)

            return template[:32]
        else:
            if clan_tag:
                template = template.replace("clan-tag", clan_tag)

            return template


    async def get_binds(self, guild):
        role_binds = await get_guild_value(guild, "roleBinds") or {}
        group_ids  = await get_guild_value(guild, "groupIDs") or {}

        role_binds["groups"]     = role_binds.get("groups", {})
        role_binds["assets"]     = role_binds.get("assets", {})
        role_binds["badges"]     = role_binds.get("badges", {})
        role_binds["gamePasses"] = role_binds.get("gamePasses", {})


        return role_binds, group_ids


    async def guild_obligations(self, member, guild, join=None, cache=True, dm=False, event=False, response=None, exceptions=None, roles=True, nickname=True, roblox_user=None):
        if member.bot:
            raise CancelCommand()

        if guild.id in IGNORED_SERVERS:
            raise CancelCommand()

        if self.pending_verifications.get(member.id):
            raise CancelCommand("You are already queued for verification. This process can take a while depending on the size of the server due to Discord rate-limits.")

        self.pending_verifications[member.id] = True

        try:
            roblox_user = None
            accounts = []
            donator_profile = None
            unverified = False
            exceptions = exceptions or ()
            added, removed, errored, warnings, chosen_nickname = [], [], [], [], None
            card = None
            embed = None
            bind_explanations = {"success": [], "failure": []}

            if RELEASE == "PRO":
                donator_profile = await has_premium(guild=guild)

                if "pro" not in donator_profile.features:
                    raise CancelCommand

            try:
                roblox_user, accounts, _ = await self.get_user(user=member, everything=True, cache=cache)
            except UserNotVerified:
                unverified = True
            except RobloxAPIError as e:
                if "RobloxAPIError" in exceptions:
                    raise RobloxAPIError from e
            except RobloxDown:
                if "RobloxDown" in exceptions:
                    raise RobloxDown
                else:
                    raise CancelCommand

            if not roblox_user:
                unverified = True

            async def post_log(channel_data, color):
                if event and channel_data:
                    if not unverified:
                        if channel_data.get("verified") and channel_data["verified"].get("channel"):
                            channel_id = int(channel_data["verified"]["channel"])
                            channel = discord.utils.find(lambda c: c.id == channel_id, guild.text_channels)

                            if channel:
                                join_channel_message = channel_data["verified"]["message"]
                                join_message_parsed = (await self.get_nickname(member, join_channel_message, roblox_user=roblox_user, dm=dm, is_nickname=False))[:1500]
                                includes = channel_data["verified"]["includes"]

                                embed   = discord.Embed(description=join_message_parsed)
                                content = None
                                view    = None
                                use_embed = False

                                if includes:
                                    embed_description_buffer = []

                                    if includes.get("robloxAvatar"):
                                        use_embed = True
                                        embed.set_thumbnail(url=roblox_user.avatar)

                                    if includes.get("robloxUsername"):
                                        use_embed = True
                                        embed_description_buffer.append(f"**Roblox username:** {roblox_user.username}")

                                    if includes.get("robloxAge"):
                                        use_embed = True
                                        embed_description_buffer.append(f"**Roblox account created:** {roblox_user.full_join_string}")

                                    if use_embed:
                                        embed.set_author(name=str(member), icon_url=member.avatar.url if member.avatar else None, url=roblox_user.profile_link)
                                        embed.set_footer(text="Disclaimer: the message above was set by the Server Admins. The ONLY way to verify with Fluxblox "
                                                            "is through https://blox.link and NO other link.")
                                        embed.colour = color

                                        view = discord.ui.View()
                                        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Visit Profile", url=roblox_user.profile_link, emoji="👥"))

                                        if embed_description_buffer:
                                            embed_description_buffer = "\n".join(embed_description_buffer)
                                            embed.description = f"{embed.description}\n\n{embed_description_buffer}"

                                if not use_embed:
                                    embed = None
                                    content = f"{join_message_parsed}\n\n**Disclaimer:** the message above was set by the Server Admins. The ONLY way to verify with Fluxblox " \
                                            "is through <https://blox.link> and NO other link."

                                if includes.get("ping"):
                                    content = f"{member.mention} {content or ''}"

                                try:
                                    await channel.send(content=content, embed=embed, view=view)
                                except (discord.errors.NotFound, discord.errors.Forbidden):
                                    pass
                    else:
                        if channel_data.get("unverified") and channel_data["unverified"].get("channel"):
                            channel_id = int(channel_data["unverified"]["channel"])
                            channel = discord.utils.find(lambda c: c.id == channel_id, guild.text_channels)

                            if channel:
                                join_channel_message = channel_data["unverified"]["message"]
                                join_message_parsed = (await self.get_nickname(member, join_channel_message, skip_roblox_check=True, dm=dm, is_nickname=False))[:2000]
                                includes = channel_data["unverified"].get("includes") or {}
                                format_embed = channel_data["unverified"].get("embed")

                                embed   = None
                                content = None

                                if format_embed:
                                    embed = discord.Embed(description=join_message_parsed)
                                    embed.set_author(name=str(member), icon_url=member.avatar.url if member.avatar else None)
                                    embed.set_footer(text="Disclaimer: the message above was set by the Server Admins. The ONLY way to verify with Fluxblox "
                                                        "is through https://blox.link and NO other link.")
                                    embed.colour = color
                                else:
                                    content = f"{join_message_parsed}\n\n**Disclaimer:** the message above was set by the Server Admins. The ONLY way to verify with Fluxblox " \
                                            "is through <https://blox.link> and NO other link."

                                if includes.get("ping"):
                                    content = f"{member.mention} {content or ''}"

                                try:
                                    await channel.send(content=content, embed=embed)
                                except (discord.errors.NotFound, discord.errors.Forbidden):
                                    pass

            if join is not False:
                options = await get_guild_value(guild, ["verifiedDM", DEFAULTS.get("welcomeMessage")], ["unverifiedDM", DEFAULTS.get("unverifiedDM")], "ageLimit", ["disallowAlts", DEFAULTS.get("disallowAlts")], ["disallowBanEvaders", DEFAULTS.get("disallowBanEvaders")], "groupLock", "joinChannel", "highTrafficServer")

                verified_dm = options.get("verifiedDM")
                join_channel = options.get("joinChannel")
                unverified_dm = options.get("unverifiedDM")
                age_limit = options.get("ageLimit")
                disallow_alts = options.get("disallowAlts")
                disallow_ban_evaders = options.get("disallowBanEvaders")
                high_traffic_server = options.get("highTrafficServer")

                if high_traffic_server:
                    dm = False

                try:
                    age_limit = int(age_limit) #FIXME
                except TypeError:
                    age_limit = None

                if disallow_alts or disallow_ban_evaders:
                    if not donator_profile:
                        donator_profile = await has_premium(guild=guild)

                    if "premium" in donator_profile.features:
                        accounts = set(accounts)

                        if roblox_user: #FIXME: temp until primary accounts are saved to the accounts array
                            accounts.add(roblox_user.id)

                        if accounts and (disallow_alts or disallow_ban_evaders):
                            for roblox_id in accounts:
                                discord_ids = await get_db_value("roblox_accounts", roblox_id, "discordIDs") or []

                                for discord_id in discord_ids:
                                    discord_id = int(discord_id)

                                    if discord_id != member.id:
                                        if disallow_alts:
                                            # check the server

                                            try:
                                                user_find = await guild.fetch_member(discord_id)
                                            except discord.errors.NotFound:
                                                pass
                                            else:
                                                if dm:
                                                    try:
                                                        await member.send(f"This server ({guild.name}) forbids the use of alterantive accounts, so your old account has been removed from the server.")
                                                    except discord.errors.Forbidden:
                                                        pass

                                                try:
                                                    await user_find.kick(reason=f"disallowAlts is enabled - alt of {member} ({member.id})")
                                                except discord.errors.Forbidden:
                                                    pass
                                                else:
                                                    await post_event(guild, "moderation", f"{user_find.mention} is an alt of {member.mention} and has been `kicked`.", RED_COLOR)

                                                    raise CancelCommand

                                        if disallow_ban_evaders:
                                            # check the bans

                                            try:
                                                ban_entry = await guild.fetch_ban(discord.Object(discord_id))
                                            except (discord.errors.NotFound, discord.errors.Forbidden):
                                                pass
                                            else:
                                                action = disallow_ban_evaders == "kick" and "kick"   or "ban"
                                                action_participle    = action == "kick" and "kicked" or "banned"

                                                if dm:
                                                    try:
                                                        await member.send(f"This server ({guild.name}) forbids ban-evaders, and as you have a banned account in the server, you have been {action_participle}.")
                                                    except discord.errors.Forbidden:
                                                        pass

                                                try:
                                                    await ((getattr(guild, action))(member, reason=f"disallowBanEvaders is enabled - alt of {ban_entry.user} ({ban_entry.user.id})"))
                                                except (discord.errors.Forbidden, discord.errors.HTTPException):
                                                    pass
                                                else:
                                                    await post_event(guild, "moderation", f"{member.mention} is an alt of {ban_entry.user.mention} and has been `{action_participle}`.", RED_COLOR)

                                                    raise CancelCommand

                                                return added, removed, chosen_nickname, errored, warnings, roblox_user, None

                try:
                    added, removed, chosen_nickname, errored, warnings, _, bind_explanations = await self.update_member(
                        member,
                        guild                   = guild,
                        roles                   = roles,
                        nickname                = nickname,
                        roblox_user             = roblox_user,
                        cache                   = cache,
                        dm                      = dm,
                        response                = response)

                except discord.errors.NotFound as e:
                    if "NotFound" in exceptions:
                        raise e from None
                except RobloxAPIError as e:
                    if "RobloxAPIError" in exceptions:
                        raise e from None
                except Error as e:
                    if "Error" in exceptions:
                        raise e from None
                except CancelCommand as e:
                    if "CancelCommand" in exceptions:
                        raise e from None
                except RobloxDown as e:
                    if "RobloxDown" in exceptions:
                        raise e from None
                    else:
                        raise CancelCommand
                except Blacklisted as e:
                    if "Blacklisted" in exceptions:
                        raise e from None
                except FluxbloxBypass as e:
                    if "FluxbloxBypass" in exceptions:
                        raise e from None
                except PermissionError as e:
                    if "PermissionError" in exceptions:
                        raise e from None

                except (UserNotVerified, discord.errors.HTTPException):
                    pass

                required_groups = options.get("groupLock")

                if roblox_user:
                    if event:
                        await post_event(guild, "verification", f"{member.mention} has **verified** as `{roblox_user.username}`.", GREEN_COLOR)

                    if age_limit:
                        if age_limit > roblox_user.age:
                            if dm:
                                try:
                                    await member.send(f"_Fluxblox Age-Limit_\nYou were kicked from **{guild.name}** for not being at least "
                                                    f"`{age_limit}` days old on your Roblox account `{roblox_user.username}` (days={roblox_user.age}). If this is a mistake, "
                                                    f"then please join {SERVER_INVITE} and link a different account with `/verify`. "
                                                    f"Finally, use the `/switchuser` command and provide this ID to the command: `{guild.id}`")
                                except discord.errors.Forbidden:
                                    pass

                            try:
                                await member.kick(reason=f"AGE-LIMIT: user age {roblox_user.age} < {age_limit}")
                            except discord.errors.Forbidden:
                                pass
                            else:
                                raise CancelCommand

                            return added, removed, chosen_nickname, errored, warnings, roblox_user, bind_explanations

                    if required_groups:
                        for group_id, group_data in required_groups.items():
                            user_group = roblox_user.groups.get(group_id)
                            group = user_group or await self.get_group(group_id, full_group=True)

                            group_lock_action = group_data.get("verifiedAction", "kick")
                            required_rolesets = group_data.get("roleSets")

                            if group_lock_action == "kick":
                                if user_group and required_rolesets:
                                    default_dm = DEFAULTS.get("groupLockKickMessageRolesetsVerified")
                                else:
                                    default_dm = DEFAULTS.get("groupLockKickMessageVerified")
                            else:
                                if user_group and required_rolesets:
                                    default_dm = DEFAULTS.get("groupLockDMMessageRolesetsVerified")
                                else:
                                    default_dm = DEFAULTS.get("groupLockDMMessageVerified")

                            dm_message_raw = group_data.get("dmMessage") or default_dm
                            dm_message = await self.get_nickname(member, dm_message_raw, guild=guild, is_nickname=False, group=user_group or group, roblox_user=roblox_user)

                            view = discord.ui.View()
                            if dm_message_raw and dm_message_raw != default_dm:
                                view.add_item(item=discord.ui.Button(label="The text above was set by the Server Admins. ONLY verify from https://blox.link.",
                                                disabled=True,
                                                custom_id="warning:modified_content_button",
                                                row=0))

                            if user_group:
                                if group_data.get("roleSets"):
                                    for allowed_roleset in group_data["roleSets"]:
                                        if isinstance(allowed_roleset, list):
                                            if allowed_roleset[0] <= user_group.user_rank_id <= allowed_roleset[1]:
                                                break
                                        else:
                                            if (user_group.user_rank_id == allowed_roleset) or (allowed_roleset < 0 and abs(allowed_roleset) <= user_group.user_rank_id):
                                                break
                                    else:
                                        if dm:
                                            try:
                                                await member.send(dm_message, view=view)
                                            except discord.errors.Forbidden:
                                                pass

                                        if group_lock_action == "kick":
                                            try:
                                                await member.kick(reason=f"SERVER-LOCK: doesn't have the allowed roleset(s) for group {group_id}")
                                            except discord.errors.Forbidden:
                                                pass
                                            else:
                                                raise CancelCommand

                                        else:
                                            raise Blacklisted(f"you do not have the required Roleset in the group [{group.name}](<{group.url}>).", guild_restriction=True)

                                        return added, removed, chosen_nickname, errored, warnings, roblox_user, bind_explanations
                            else:
                                if dm:
                                    try:
                                        await member.send(dm_message, view=view)
                                    except discord.errors.Forbidden:
                                        pass

                                if group_lock_action == "kick":
                                    try:
                                        await member.kick(reason=f"SERVER-LOCK: not in group {group_id}")
                                    except discord.errors.Forbidden:
                                        pass
                                    else:
                                        raise CancelCommand
                                else:
                                    raise Blacklisted(f"you are not in the required group [{group.name}](<{group.url}>). Please join [{group.name}](<{group.url}>) then run this command again.", guild_restriction=True)


                                return added, removed, chosen_nickname, errored, warnings, roblox_user, bind_explanations

                    if dm and verified_dm:
                        if verified_dm != DEFAULTS.get("welcomeMessage"):
                            verified_dm = f"This message was set by the Server Admins:\n{verified_dm}"

                        verified_dm = (await self.get_nickname(member, verified_dm, roblox_user=roblox_user, dm=dm, is_nickname=False))[:2000]

                        _, card, embed, view = await self.format_update_embed(
                            roblox_user,
                            member,
                            guild=guild,
                            added=added, removed=removed, errors=errored, warnings=warnings, nickname=chosen_nickname,
                            from_interaction=False
                        )

                        try:
                            msg = await member.send(verified_dm, files=[card.front_card_file] if card else None, view=card.view if card else view, embed=embed)
                        except (discord.errors.Forbidden, discord.errors.HTTPException):
                            pass
                        else:
                            if card:
                                card.response = member
                                card.message = msg
                                card.view.message = msg

                    if join is not None:
                        await post_log(join_channel, GREEN_COLOR)

                else:
                    if age_limit:
                        if not donator_profile:
                            donator_profile = await has_premium(guild=guild)

                        if "premium" in donator_profile.features:
                            if dm:
                                try:
                                    if accounts:
                                        await member.send(f"_Fluxblox Server-Lock_\nYou have no primary account set! Please go to <{VERIFY_URL}> and set a "
                                                          "primary account, then try rejoining this server.")
                                    else:
                                        await member.send(f"_Fluxblox Server-Lock_\nYou were kicked from **{guild.name}** for not being linked to Fluxblox.\n"
                                                          f"You may link your account to Fluxblox by visiting <{VERIFY_URL}> and completing the verification process.\n"
                                                          "Stuck? Watch this video: <https://youtu.be/0SH3n8rY9Fg>\n"
                                                          f"Join {SERVER_INVITE} for additional help.")
                                except discord.errors.Forbidden:
                                    pass

                            try:
                                await member.kick(reason=f"AGE-LIMIT: user not linked to Fluxblox")
                            except discord.errors.Forbidden:
                                pass
                            else:
                                raise CancelCommand

                            return added, removed, chosen_nickname, errored, warnings, roblox_user, bind_explanations

                    if required_groups:
                        should_kick_unverified = any(g.get("unverifiedAction", "kick") == "kick" for g in required_groups.values())

                        if dm:
                            if should_kick_unverified:
                                dm_message = DEFAULTS.get("kickMessageNotVerified")
                            else:
                                dm_message = DEFAULTS.get("DMMessageNotVerified")

                            dm_message = await self.get_nickname(member, dm_message, guild=guild, is_nickname=False, roblox_user=None, skip_roblox_check=True)

                            try:
                                if accounts:
                                    await member.send(f"You have no primary account set! Please go to <{VERIFY_URL}> and set a "
                                                      "primary account, then try rejoining this server.")
                                else:
                                    if should_kick_unverified:
                                        await member.send(f"You were kicked from **{guild.name}** for not being linked to Fluxblox.\n\n"
                                                          f"**How to fix this:** Go to <" + VERIFY_URL + "> to verify with Fluxblox.\n\n"
                                                          "**Stuck? Watch this video:** <https://www.youtube.com/watch?v=mSbD91Zug5k&t=0s>\n\n"
                                                          f"Join {SERVER_INVITE} for additional help.")
                                    else:
                                        await member.send(f"{guild.name} requires that you verify with Fluxblox in order to access the rest of the server.\n\n"
                                                          f"**How to fix this:** Go to <" + VERIFY_URL + "> to verify with Fluxblox.")

                            except discord.errors.Forbidden:
                                pass

                        if should_kick_unverified:
                            try:
                                await member.kick(reason="GROUP-LOCK: not linked to Fluxblox")
                            except discord.errors.Forbidden:
                                pass
                            else:
                                raise CancelCommand

                        return added, removed, chosen_nickname, errored, warnings, roblox_user, bind_explanations

                    if dm and unverified_dm:
                        unverified_dm = await self.get_nickname(member, unverified_dm, skip_roblox_check=True, dm=dm, is_nickname=False)

                        try:
                            await member.send(unverified_dm)
                        except (discord.errors.Forbidden, discord.errors.HTTPException):
                            pass

                    await post_log(join_channel, GREEN_COLOR)

                if not unverified:
                    return added, removed, chosen_nickname, errored, warnings, roblox_user, bind_explanations
                else:
                    if "UserNotVerified" in exceptions:
                        raise UserNotVerified

                    bind_explanations["success"].append(["unverified role", None, None, "You are not verified on Fluxblox.", ])

                    return added, removed, chosen_nickname, errored, warnings, roblox_user, bind_explanations

            elif join == False:
                leave_channel = await get_guild_value(guild, "leaveChannel")

                await post_log(leave_channel, RED_COLOR)

            if unverified and "UserNotVerified" in exceptions:
                raise UserNotVerified

        finally:
            self.pending_verifications.pop(member.id, None)

    # async def get_binds_for_user(self, user, guild, *, guild_data=None, roblox_user=None, cache=False):
    #     """return the required and optional binds for the user"""

    #     required_binds, optional_binds = {
    #         "add": {
    #             "verifiedRole": None,
    #             "binds": []
    #         },
    #         "remove": {
    #             "verifiedRole": None,
    #             "binds": []
    #         }
    #     }, {
    #         "add": {
    #             "verifiedRole": None,
    #             "binds": []
    #         },
    #         "remove": {
    #             "verifiedRole": None,
    #             "binds": []
    #         }
    #     }

    #     unverified = False

    #     if not isinstance(user, discord.Member):
    #         user = await guild.fetch_member(user.id)

    #         if not user:
    #             raise CancelCommand

    #     if not guild:
    #         guild = getattr(user, "guild", None)

    #         if not guild:
    #             raise Error("Unable to resolve a guild from user.")

    #     guild_data = guild_data or await self.r.table("guilds").get(str(guild.id)).run() or {}

    #     if await has_magic_role(user, guild, "Fluxblox Bypass"):
    #         raise FluxbloxBypass()

    #     verify_role   = guild_data.get("verifiedRoleEnabled", DEFAULTS.get("verifiedRoleEnabled"))
    #     unverify_role = guild_data.get("unverifiedRoleEnabled", DEFAULTS.get("unverifiedRoleEnabled"))

    #     unverified_role_name = guild_data.get("unverifiedRoleName", DEFAULTS.get("unverifiedRoleName"))
    #     verified_role_name   = guild_data.get("verifiedRoleName", DEFAULTS.get("verifiedRoleName"))

    #     if unverify_role:
    #         unverified_role = discord.utils.find(lambda r: r.name == unverified_role_name and not r.managed, guild.roles)

    #     if verify_role:
    #         verified_role = discord.utils.find(lambda r: r.name == verified_role_name and not r.managed, guild.roles)

    #     try:
    #         if not roblox_user:
    #             roblox_user = (await self.get_user(user=user, guild=guild, everything=True, cache=cache))[0]

    #             if not roblox_user:
    #                 raise UserNotVerified

    #     except UserNotVerified:
    #         if unverify_role:
    #             if not unverified_role:
    #                 try:
    #                     unverified_role = await guild.create_role(name=unverified_role_name)
    #                 except discord.errors.Forbidden:
    #                     raise PermissionError("I was unable to create the Unverified Role. Please "
    #                                             "ensure I have the `Manage Roles` permission.")
    #                 except discord.errors.HTTPException:
    #                     raise Error("Unable to create role: this server has reached the max amount of roles!")

    #             required_binds["add"]["unverifiedRole"] = unverified_role

    #         if verify_role and verified_role and verified_role in user.roles:
    #             required_binds["remove"]["verifiedRole"] = verified_role

    #         nickname = await self.get_nickname(user=user, skip_roblox_check=True, guild=guild, guild_data=guild_data, dm=dm, response=response)

    #         unverified = True

    #     else:
    #         restriction = await check_restrictions("robloxAccounts", roblox_user.id, guild=guild, roblox_user=roblox_user)

    #         if restriction:
    #             raise Blacklisted(restriction)

    #         if unverify_role:
    #             if unverified_role and unverified_role in user.roles:
    #                 required_binds["remove"]["unverifiedRole"] = unverified_role

    #         if verify_role:
    #             verified_role = discord.utils.find(lambda r: r.name == verified_role_name and not r.managed, guild.roles)

    #             if not verified_role:
    #                 try:
    #                     verified_role = await guild.create_role(
    #                         name   = verified_role_name,
    #                         reason = "Creating missing Verified role"
    #                     )
    #                 except discord.errors.Forbidden:
    #                     raise PermissionError("Sorry, I wasn't able to create the Verified role. "
    #                                           "Please ensure I have the `Manage Roles` permission.")
    #                 except discord.errors.HTTPException:
    #                     raise Error("Unable to create role: this server has reached the max amount of roles!")

    #             required_binds["add"]["verifiedRole"] = verified_role

    #     if not unverified:
    #         role_binds, group_ids, _ = await self.get_binds(guild)

    #         for category, binds in role_binds.items():
    #             if category == "groups":
    #                 for group_id, group_bind_data in binds.items():
    #                     user_group = roblox_user.groups.get(group_id)

    #                     for bind_id, bind_data in group_bind_data.get("binds", {}).items():
    #                         bind_remove_roles = bind_data.get("removeRoles") or []
    #                         bound_roles = bind_data.get("roles")

    #                         try:
    #                             rank = int(bind_id)
    #                         except ValueError:
    #                             rank = None

    #                         if user_group:
    #                             if bind_id == "0":
    #                                 if bound_roles:
    #                                     # if the user has these roles, remove them
    #                                     pass

    #                             if (bind_id == "all" or user_group.user_rank_id == bind_id) or (rank and (rank < 0 and user_group.user_rank_id >= abs(rank))):
    #                                 required_binds["add"]["binds"].append(bind_data)

    #                                 for role_id in bind_remove_roles:
    #                                     # if the user has these roles, remove them
    #                                     pass
    #                             else:
    #                                 for role_id in bound_roles:
    #                                     # if user has these roles, remove them
    #                                     pass
    #                         else:
    #                             if bind_id == "0":
    #                                 if bound_roles:
    #                                     required_binds["add"]["binds"].append(bind_data)

    #                                 for role_id in bind_remove_roles:
    #                                     # if the user has these roles, remove them
    #                                     pass
    #                             else:
    #                                 if bound_roles:
    #                                     # if the user has these roles, remove them
    #                                     pass

    #                     for bind_range in group_bind_data.get("ranges", []):
    #                         bound_roles = bind_range.get("roles", set())
    #                         bind_remove_roles = bind_range.get("removeRoles") or []

    #                         if user_group:
    #                             user_rank = user_group.user_rank_id

    #                             if bind_range["low"] <= user_rank <= bind_range["high"]:
    #                                 required_binds["add"]["binds"].append(bind_data)

    #                                 for role_id in bind_remove_roles:
    #                                     # if the user has these roles, remove them
    #                                     pass
    #                             else:
    #                                 required_binds["remove"]["binds"].append(bind_range)

    #                         else:
    #                             # if the user has these roles, remove them
    #                             pass




    #     return required_binds, optional_binds

    # async def apply_binds(user, required_binds, optional_binds):
    #     """given binds, apply them to the user"""

    #     pass



    # async def update_member_new(self, user, guild=None, *, nickname=True, roles=True):
    #     """get the binds and apply them to the user"""

    #     guild = guild or getattr(user, "guild", None)

    #     if not guild:
    #         raise CancelCommand

    #     required_binds, optional_binds = await self.get_binds_for_user(user, guild)

    #     await self.apply_binds(user, required_binds, optional_binds)

    #     print(required_binds)
    #     print(optional_binds)

    async def update_member(self, user, guild, *, nickname=True, roles=True, group_roles=True, roblox_user=None, binds=None, response=None, dm=False, cache=True):
        await check_restrictions("users", user.id, guild=guild)

        if not cache:
            await cache_pop(f"discord_profiles:{user.id}")

        me = getattr(guild, "me", None)
        my_permissions = me and me.guild_permissions

        if my_permissions:
            if roles and not my_permissions.manage_roles:
                raise PermissionError("Sorry, I do not have the proper permissions. "
                                      "Please ensure I have the `Manage Roles` permission.")

            if nickname and not my_permissions.manage_nicknames:
                raise PermissionError("Sorry, I do not have the proper permissions. "
                                      "Please ensure I have the `Manage Nicknames` permission.")

        add_roles, remove_roles = set(), set()
        possible_nicknames = []
        errors = []
        warnings = []
        unverified = False
        top_role_nickname = None

        bind_explanations = {"success": [], "failure": [], "criteria": []}

        if not isinstance(user, discord.Member):
            user = await guild.fetch_member(user.id)

            if not user:
                raise CancelCommand

        if not guild:
            guild = getattr(user, "guild", None)

            if not guild:
                raise Error("Unable to resolve a guild from user.")

        if await has_magic_role(user, guild, "Fluxblox Bypass"):
            raise FluxbloxBypass()


        async def give_bind_stuff(binds):
            bind_nickname = binds.get("nickname")
            bound_roles = binds.get("roles")
            bind_remove_roles = binds.get("removeRoles") or []

            for role_id in bound_roles:
                int_role_id = role_id.isdigit() and int(role_id)
                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                if role:
                    add_roles.add(role)

                    if nickname and bind_nickname and bind_nickname != "skip":
                        if user.top_role == role:
                            top_role_nickname = await self.get_nickname(user=user, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                        resolved_nickname = await self.get_nickname(user=user, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                        if resolved_nickname and not resolved_nickname in possible_nicknames:
                            possible_nicknames.append([role, resolved_nickname])

            for role_id in bind_remove_roles:
                int_role_id = role_id.isdigit() and int(role_id)
                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, user.roles)

                if role:
                    remove_roles.add(role)

        async def remove_bind_stuff(binds):
            bound_roles = binds.get("roles")

            for role_id in bound_roles:
                int_role_id = role_id.isdigit() and int(role_id)
                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, user.roles)

                if role and not allow_old_roles:
                    remove_roles.add(role)

        options = await get_guild_value(guild,
                                        ["verifiedRoleEnabled",   DEFAULTS.get("verifiedRoleEnabled")],
                                        ["unverifiedRoleEnabled", DEFAULTS.get("unverifiedRoleEnabled")],
                                        ["unverifiedRoleName",    DEFAULTS.get("unverifiedRoleName")],
                                        ["verifiedRoleName",      DEFAULTS.get("verifiedRoleName")],
                                        ["allowOldRoles",         DEFAULTS.get("allowOldRoles")],
                                        ["nicknameTemplate",      DEFAULTS.get("nicknameTemplate")],
                                        "verifiedRole",
                                        "unverifiedRole",)

        verify_role_enabled   = options.get("verifiedRoleEnabled")
        unverify_role_enabled = options.get("unverifiedRoleEnabled")

        unverified_role_name = options.get("unverifiedRoleName") or DEFAULTS.get("unverifiedRoleName")
        verified_role_name   = options.get("verifiedRoleName") or DEFAULTS.get("verifiedRoleName")

        allow_old_roles = options.get("allowOldRoles")

        nickname_template = options.get("nicknameTemplate")

        verified_role_id   = int(options.get("verifiedRole")) if options.get("verifiedRole") else None
        unverified_role_id = int(options.get("unverifiedRole")) if options.get("unverifiedRole") else None

        verified_role = None
        unverified_role = None

        if unverify_role_enabled:
            if unverified_role_id:
                unverified_role = discord.utils.find(lambda r: (r.id == unverified_role_id) and not r.managed, guild.roles)

            if not unverified_role:
                unverified_role = discord.utils.find(lambda r: (r.name == unverified_role_name.strip()) and not r.managed, guild.roles)

            if not unverified_role:
                try:
                    unverified_role = await guild.create_role(name=unverified_role_name, reason="Creating missing Unverified role")
                except discord.errors.Forbidden:
                    raise PermissionError("I was unable to create the Unverified Role. Please "
                                          "ensure I have the `Manage Roles` permission.")
                except discord.errors.HTTPException:
                    raise Error("Unable to create role: this server has reached the max amount of roles!")


        if verify_role_enabled:
            if verified_role_id:
                verified_role = discord.utils.find(lambda r: (r.id == verified_role_id) and not r.managed, guild.roles)

            if not verified_role:
                verified_role = discord.utils.find(lambda r: (r.name == verified_role_name.strip()) and not r.managed, guild.roles)

            if not verified_role:
                try:
                    verified_role = await guild.create_role(
                        name   = verified_role_name,
                        reason = "Creating missing Verified role"
                    )
                except discord.errors.Forbidden:
                    raise PermissionError("Sorry, I wasn't able to create the Verified role. "
                                          "Please ensure I have the `Manage Roles` permission.")
                except discord.errors.HTTPException:
                    raise Error("Unable to create role: this server has reached the max amount of roles!")

        try:
            if not roblox_user:
                roblox_user = (await self.get_user(user=user, guild=guild, everything=True, cache=cache))[0]

                if not roblox_user:
                    raise UserNotVerified

        except UserNotVerified:
            if roles:
                if unverify_role_enabled:
                    add_roles.add(unverified_role)
                    bind_explanations["success"].append(["unverified role", None, None, "You are not verified on Fluxblox.", [unverified_role.name]])

                if verify_role_enabled and verified_role and verified_role in user.roles:
                    remove_roles.add(verified_role)

            if nickname:
                nickname = await self.get_nickname(user=user, skip_roblox_check=True, guild=guild, dm=dm, response=response)

            unverified = True

        else:
            await check_restrictions("robloxAccounts", roblox_user.id, guild=guild, roblox_user=roblox_user)

            if roles:
                if unverified_role:
                    if unverified_role and unverified_role in user.roles:
                        remove_roles.add(unverified_role)

                if verified_role:
                    add_roles.add(verified_role)
                    bind_explanations["success"].append(["verified role", None, None, "You are verified on Fluxblox.", [verified_role.name]])

        if not unverified:
            if group_roles and roblox_user:
                if binds and len(binds) == 2 and binds[0] is not None and binds[1] is not None:
                    role_binds, group_ids = binds
                else:
                    role_binds, group_ids = await self.get_binds(guild)

                if role_binds:
                    if isinstance(role_binds, list):
                        role_binds = role_binds[0]

                    for category, all_binds in role_binds.items():
                        if category in ("assets", "badges", "gamePasses"):
                            if category == "gamePasses":
                                category_title = "GamePass"
                            else:
                                category_title = (category[:-1]).title()

                            for bind_id, bind_data in all_binds.items():
                                bind_nickname = bind_data.get("nickname")
                                bound_roles = bind_data.get("roles")
                                bind_remove_roles = bind_data.get("removeRoles") or []

                                json_data, response_ = await fetch(f"https://inventory.roblox.com/v1/users/{roblox_user.id}/items/{category_title}/{bind_id}", json=True, raise_on_failure=False)

                                if isinstance(json_data, dict):
                                    if response_.status != 200:
                                        vg_errors = json_data.get("errors", [])

                                        if vg_errors:
                                            error_message = vg_errors[0].get("message")

                                            if error_message != "The specified user does not exist!": # sent if someone is banned from Roblox
                                                raise Error(f"Bind error for {category_title} ID {bind_id}: `{error_message}`")
                                        else:
                                            raise Error(f"Bind error for {category_title} ID {bind_id}")

                                    if json_data.get("data"):
                                        # TODO: cache this
                                        asset_roles = []

                                        for role_id in bound_roles:
                                            int_role_id = role_id.isdigit() and int(role_id)
                                            role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                                            if role:
                                                add_roles.add(role)
                                                asset_roles.append(role.name)

                                            if role and nickname and bind_nickname and bind_nickname != "skip":
                                                if user.top_role == role:
                                                    top_role_nickname = await self.get_nickname(user=user, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                                resolved_nickname = await self.get_nickname(user=user, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                                if resolved_nickname and not resolved_nickname in possible_nicknames:
                                                    possible_nicknames.append([role, resolved_nickname])

                                        bind_explanations["success"].append([category_title.lower(), bind_id, json_data["data"][0].get("name"), f"You own this {category_title.lower()}.", asset_roles])

                                        for role_id in bind_remove_roles:
                                            int_role_id = role_id.isdigit() and int(role_id)
                                            role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, user.roles)

                                            if role:
                                                remove_roles.add(role)
                                    else:
                                        explanation_roles = []

                                        for role_id in bound_roles:
                                            int_role_id = role_id.isdigit() and int(role_id)
                                            role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                                            if role:
                                                if not allow_old_roles and role in user.roles:
                                                    remove_roles.add(role)

                                                explanation_roles.append(role.name)

                                        bind_explanations["failure"].append([category_title.lower(), bind_id, bind_data.get("displayName"), f"You do not own this {category_title.lower()}.", explanation_roles])

                        elif category == "robloxStaff":
                            devforum_data = roblox_user.dev_forum

                            if devforum_data and devforum_data.get("trust_level") == 4:
                                await give_bind_stuff(all_binds)
                            else:
                                await remove_bind_stuff(all_binds)

                        elif category == "devForum":
                            devforum_data = roblox_user.dev_forum

                            if devforum_data and devforum_data.get("trust_level"):
                                await give_bind_stuff(all_binds)
                            else:
                                await remove_bind_stuff(all_binds)

                        elif category == "groups":
                            for group_id, data in all_binds.items():
                                group = roblox_user.groups.get(group_id)

                                for bind_id, bind_data in data.get("binds", {}).items():
                                    rank = None
                                    bind_nickname = bind_data.get("nickname")
                                    bound_roles = bind_data.get("roles") or {}
                                    bind_remove_roles = bind_data.get("removeRoles") or []

                                    try:
                                        rank = int(bind_id)
                                    except ValueError:
                                        pass

                                    if group:
                                        user_rank = group.user_rank_id

                                        if bind_id == "0":
                                            if bound_roles:
                                                for role_id in bound_roles:
                                                    int_role_id = role_id.isdigit() and int(role_id)
                                                    role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, user.roles)

                                                    if role and not allow_old_roles:
                                                        remove_roles.add(role)

                                        elif (bind_id == "all" or rank == user_rank) or (rank and (rank < 0 and user_rank >= abs(rank))):
                                            if not bound_roles:
                                                bound_roles = {group.user_rank_name}

                                            explanation_roles = []

                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                                                if role:
                                                    add_roles.add(role)
                                                    explanation_roles.append(role.name)

                                                if role and nickname and bind_nickname and bind_nickname != "skip":
                                                    if user.top_role == role:
                                                        top_role_nickname = await self.get_nickname(user=user, group=group, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                                    resolved_nickname = await self.get_nickname(user=user, group=group, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                                    if resolved_nickname and not resolved_nickname in possible_nicknames:
                                                        possible_nicknames.append([role, resolved_nickname])

                                            if bind_id == "all":
                                                bind_explanations["success"].append(["group", group_id, group.name, "You are in the group.", explanation_roles])
                                            elif rank == user_rank:
                                                bind_explanations["success"].append(["group", group_id, group.name, f"Your rank, {user_rank}, is the exact match for this bind.", explanation_roles])
                                            elif rank and (rank < 0 and user_rank >= abs(rank)):
                                                bind_explanations["success"].append(["group", group_id, group.name, f"Your rank, {user_rank}, is at least {abs(rank)}.", explanation_roles])

                                            for role_id in bind_remove_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, user.roles)

                                                if role:
                                                    remove_roles.add(role)

                                        else:
                                            explanation_roles = []

                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                                                if role:
                                                    if not allow_old_roles and role in user.roles:
                                                        remove_roles.add(role)

                                                    explanation_roles.append(role.name)

                                            if bind_id == "all":
                                                bind_explanations["failure"].append(["group", group_id, bind_data.get("groupName"), "You must be in the group.", explanation_roles])
                                            elif rank and (rank < 0 and user_rank >= abs(rank)):
                                                bind_explanations["failure"].append(["group", group_id, group.name, f"Your rank, {user_rank}, is not greater than or equal to {rank}.", explanation_roles])
                                            else:
                                                bind_explanations["failure"].append(["group", group_id, group.name, f"Your rank, {user_rank}, is not equal to {rank}.", explanation_roles])


                                    else:
                                        if bind_id == "0":
                                            if bound_roles:
                                                explanation_roles = []

                                                for role_id in bound_roles:
                                                    int_role_id = role_id.isdigit() and int(role_id)
                                                    role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                                                    if role:
                                                        add_roles.add(role)
                                                        explanation_roles.append(role.name)

                                                    if role and nickname and bind_nickname and bind_nickname != "skip":
                                                        if user.top_role == role:
                                                            top_role_nickname = await self.get_nickname(user=user, group=group, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                                        resolved_nickname = await self.get_nickname(user=user, group=group, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                                        if resolved_nickname and not resolved_nickname in possible_nicknames:
                                                            possible_nicknames.append([role, resolved_nickname])

                                                bind_explanations["success"].append(["group", group_id, "You are not in this group.", explanation_roles])

                                            for role_id in bind_remove_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, user.roles)

                                                if role:
                                                    remove_roles.add(role)
                                        else:
                                            explanation_roles = []

                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                                                if role:
                                                    if not allow_old_roles and role in user.roles:
                                                        remove_roles.add(role)

                                                    explanation_roles.append(role.name)

                                            if bind_id == "all":
                                                bind_explanations["failure"].append(["group", group_id, data.get("groupName"), "You must be in the group.", explanation_roles])
                                            elif rank and rank < 0:
                                                bind_explanations["failure"].append(["group", group_id, data.get("groupName"), f"You must be in the group and your rank must be greater than or equal to {abs(rank)}.", explanation_roles])
                                            else:
                                                bind_explanations["failure"].append(["group", group_id, data.get("groupName"), f"You must be in the group and your rank must equal {rank}.", explanation_roles])

                                for bind_range in data.get("ranges", []):
                                    bind_nickname = bind_range.get("nickname")
                                    bound_roles = bind_range.get("roles", set())
                                    bind_remove_roles = bind_range.get("removeRoles") or []

                                    if group:
                                        user_rank = group.user_rank_id

                                        if int(bind_range["low"]) <= user_rank <= int(bind_range["high"]):
                                            if not bound_roles:
                                                bound_roles = {group.user_rank_name}

                                            range_roles = []

                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                                                if role:
                                                    if roles:
                                                        add_roles.add(role)
                                                        range_roles.append(role.name)

                                                        if nickname and user.top_role == role and bind_nickname:
                                                            top_role_nickname = await self.get_nickname(user=user, group=group, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                                    if nickname and bind_nickname and bind_nickname != "skip":
                                                        resolved_nickname = await self.get_nickname(user=user, group=group, template=bind_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                                        if resolved_nickname and not resolved_nickname in possible_nicknames:
                                                            possible_nicknames.append([role, resolved_nickname])

                                            bind_explanations["success"].append(["group", group_id, group.name, f"Your rank, {user_rank}, is within the range of ({bind_range['low']}, {bind_range['high']}).", range_roles])

                                            for role_id in bind_remove_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, user.roles)

                                                if role:
                                                    remove_roles.add(role)
                                        else:
                                            explanation_roles = []

                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                                                if role:
                                                    if not allow_old_roles and role in user.roles:
                                                        remove_roles.add(role)

                                                    explanation_roles.append(role.name)

                                            bind_explanations["failure"].append(["group", group_id, group.name, f"Your rank, {user_rank}, is not within the range of ({bind_range['low']}, {bind_range['high']}).", explanation_roles])

                                    else:
                                        explanation_roles = []

                                        for role_id in bound_roles:
                                            int_role_id = role_id.isdigit() and int(role_id)
                                            role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, guild.roles)

                                            if role:
                                                if not allow_old_roles and role in user.roles:
                                                    remove_roles.add(role)

                                                explanation_roles.append(role.name)

                                        bind_explanations["failure"].append(["group", group_id, data.get("groupName"), f"You must be in the group and your rank must be within the range of ({bind_range['low']}, {bind_range['high']}).", explanation_roles])

                if group_roles and group_ids:
                    for group_id, group_data in group_ids.items():
                        group_nickname = group_data.get("nickname")
                        bind_remove_roles = group_data.get("removeRoles") or []

                        if group_id != "0":
                            group = roblox_user.groups.get(str(group_id))

                            if group:
                                await group.apply_rolesets()
                                group_role = discord.utils.find(lambda r: r.name == group.user_rank_name.strip() and not r.managed, guild.roles)

                                if not group_role:
                                    dynamic_roles = await get_guild_value(guild, ["dynamicRoles", DEFAULTS.get("dynamicRoles")])
                                    if dynamic_roles:
                                        try:
                                            group_role = await guild.create_role(name=group.user_rank_name, reason="Creating missing group role")
                                        except discord.errors.Forbidden:
                                            raise PermissionError(f"Sorry, I wasn't able to create the role {group.user_rank_name}."
                                                                   "Please ensure I have the `Manage Roles` permission.")

                                        except discord.errors.HTTPException:
                                            raise Error("Unable to create role: this server has reached the max amount of roles!")

                                for _, roleset_data in group.rolesets.items():
                                    has_role = discord.utils.find(lambda r: r.name == roleset_data[0].strip() and not r.managed, user.roles)

                                    if has_role:
                                        if not allow_old_roles and group.user_rank_name != roleset_data[0]:
                                            remove_roles.add(has_role)

                                if group_role:
                                    add_roles.add(group_role)
                                    bind_explanations["success"].append(["group", group_id, group.name, "You are in this group.", [group_role.name]])

                                    for role_id in bind_remove_roles:
                                        int_role_id = role_id.isdigit() and int(role_id)
                                        role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == str(role_id).strip()) and not r.managed, user.roles)

                                        if role:
                                            remove_roles.add(role)

                                if nickname and group_nickname and group_role:
                                    if user.top_role == group_role and group_nickname:
                                        top_role_nickname = await self.get_nickname(user=user, group=group, template=group_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                    if group_nickname and group_nickname != "skip":
                                        resolved_nickname = await self.get_nickname(user=user, group=group, template=group_nickname, roblox_user=roblox_user, dm=dm, response=response)

                                        if resolved_nickname and not resolved_nickname in possible_nicknames:
                                            possible_nicknames.append([group_role, resolved_nickname])
                            else:
                                explanation_roles = []

                                try:
                                    group = await self.get_group(group_id, full_group=False)
                                except RobloxNotFound:
                                    raise Error(f"Error for linked group bind: group `{group_id}` not found")

                                for _, roleset_data in group.rolesets.items():
                                    group_role = discord.utils.find(lambda r: r.name == roleset_data[0].strip() and not r.managed, user.roles)

                                    if not allow_old_roles and group_role:
                                        remove_roles.add(group_role)
                                        explanation_roles.append(group_role.name)

                                bind_explanations["failure"].append(["group", group_id, group.name, "You are not in this group.", explanation_roles])

        if roles:
            remove_roles = remove_roles.difference(add_roles)
            add_roles = add_roles.difference(user.roles)

            try:
                for role in (*add_roles, *remove_roles):
                    if role.position > me.top_role.position:
                        raise PermissionError(f"Sorry, I can't add or remove roles above my highest role.\nPlease move the **{role}** role to a lower position or my highest role, **{me.top_role}**, higher.")

                if add_roles:
                    await user.add_roles(*add_roles, reason="Adding group roles")

                if remove_roles:
                    await user.remove_roles(*remove_roles, reason="Removing old roles")

            except discord.errors.Forbidden:
                raise PermissionError("I was unable to sufficiently add roles to the user. Please ensure that "
                                      "I have the `Manage Roles` permission, and drag my role above the other roles. ")

            except discord.errors.NotFound:
                raise CancelCommand

        if nickname:
            if not unverified:
                if possible_nicknames:
                    if len(possible_nicknames) == 1:
                        nickname = possible_nicknames[0][1]
                    else:
                        # get highest role with a nickname
                        highest_role = sorted(possible_nicknames, key=lambda e: e[0].position, reverse=True)

                        if highest_role:
                            nickname = highest_role[0][1]
                else:
                    nickname = top_role_nickname or await self.get_nickname(template=nickname_template, user=user, roblox_user=roblox_user, dm=dm, response=response)

                if isinstance(nickname, bool):
                    nickname = self.get_nickname(template=nickname_template, roblox_user=roblox_user, user=user, dm=dm, response=response)

            if nickname and nickname != user.display_name:
                try:
                    await user.edit(nick=nickname)
                except discord.errors.Forbidden:
                    if guild.owner_id == user.id:
                        warnings.append("Since you're the Server Owner, I cannot edit your nickname. You may ignore this message; verification will work for normal users.")
                    else:
                        errors.append(f"I was unable to edit your nickname. Please ensure I have the Manage Nickname permission, and drag my role above the other roles.")
                except discord.errors.NotFound:
                    raise CancelCommand

        if unverified:
            raise UserNotVerified()

        if not roblox_user:
            roblox_user = (await self.get_user(user=user, guild=guild, everything=True))[0]

        return [r.name for r in add_roles], [r.name for r in remove_roles], nickname, errors, warnings, roblox_user, bind_explanations

    async def get_group_shout(self, group_id):
        """gets the group shout. not cached."""

        text, response = await fetch(f"https://groups.roblox.com/v1/groups/{group_id}", raise_on_failure=False)

        if response.status == 404:
            raise RobloxNotFound

        elif response.status >= 500:
            raise RobloxDown

        try:
            response = json.loads(text)
            return response

        except json.decoder.JSONDecodeError:
            return {}

    @staticmethod
    async def get_game(game_id=None, game_name=None):
        if not (game_id or game_name):
            raise BadUsage("Must supply a game ID or game name to get_game")

        game = await cache_get(f"games:{game_id or game_name}")

        if game:
            return game

        if game_id:
            json_data, _ = await fetch(f"{API_URL}/marketplace/productinfo?assetId={game_id}", json=True, raise_on_failure=False)

            if json_data.get("AssetTypeId", 0) == 9:
                game = Game(str(game_id), json_data)

                await cache_set(f"games:{game_id}", game)

                return game
        else:
            json_data, _ = await fetch(f"https://games.roblox.com/v1/games/list?model.keyword={game_name}", json=True, raise_on_failure=False)

            if json_data.get("games"):
                game_data = json_data["games"][0]
                game = Game(str(game_data["placeId"]), game_data)


        raise RobloxNotFound

    @staticmethod
    async def get_catalog_item(item_id):
        item_id = str(item_id)
        item = await cache_get(f"catalog_items:{item_id}")

        if item:
            return item

        json_data, _ = await fetch(f"{API_URL}/marketplace/productinfo?assetId={item_id}", json=True, raise_on_failure=False)

        if json_data.get("AssetTypeId", 0) != 6:
            item = RobloxItem(item_id, json_data)

            await cache_set(f"catalog_items:{item_id}", item)

            return item


        raise RobloxNotFound


    @staticmethod
    async def get_group(group_id, full_group=False):
        group_id = str(group_id)

        if not group_id.isdigit():
            regex_search_group = roblox_group_regex.search(group_id)

            if regex_search_group:
                group_id = regex_search_group.group(1)

        group = await cache_get(f"groups:{group_id}")

        if group:
            if full_group:
                if group.name:
                    return group
            else:
                return group

        json_data, roleset_response = await fetch(f"{GROUP_API}/v1/groups/{group_id}/roles", json=True, raise_on_failure=False)

        if roleset_response.status == 200:
            if full_group:
                group_data, group_data_response = await fetch(f"{GROUP_API}/v1/groups/{group_id}", json=True, raise_on_failure=False)

                if group_data_response.status == 200:
                    json_data.update(group_data)

                emblem_data, emblem_data_response = await fetch(f"{THUMBNAIL_API}/v1/groups/icons?groupIds={group_id}&size=150x150&format=Png&isCircular=false", json=True, raise_on_failure=False)

                if emblem_data_response.status == 200:
                    emblem_data = emblem_data.get("data")

                    if emblem_data:
                        emblem_data = emblem_data[0]
                        json_data.update({"imageUrl": emblem_data.get("imageUrl")})

            if not group:
                group = Group(group_id=group_id, group_data=json_data)
            else:
                group.load_json(json_data)

            await cache_set(f"groups:{group_id}", group)

            return group

        elif roleset_response.status >= 500:
            raise RobloxDown

        raise RobloxNotFound

    async def get_accounts(self, user, parse_accounts=False):
        roblox_accounts = await get_user_value(user, "robloxAccounts") or {}
        roblox_ids = roblox_accounts.get("accounts", [])

        accounts = {}
        tasks = []

        for roblox_id in roblox_ids:
            roblox_user = RobloxUser(roblox_id=roblox_id)
            accounts[roblox_user.id] = roblox_user

            if parse_accounts:
                tasks.append(roblox_user.sync("username", "id", everything=False, basic_details=False))

        if parse_accounts:
            await asyncio.wait(tasks)

        return accounts

    async def get_user(self, *args, user=None, author=None, guild=None, username=None, roblox_id=None, everything=False, basic_details=True, group_ids=None, return_embed=False, cache=True):
        guild = guild or getattr(user, "guild", False)
        guild_id = guild and str(guild.id)

        roblox_account = discord_profile = None
        accounts = []
        embed = None

        if user:
            user_id = str(user.id)

            if cache:
                discord_profile = await cache_get(f"discord_profiles:{user_id}")

                if discord_profile:
                    if guild:
                        roblox_account = discord_profile.guilds.get(guild_id)
                    else:
                        roblox_account = discord_profile.primary_account

                    if roblox_account:
                        embed = await roblox_account.sync(*args, user=user, author=author, group_ids=group_ids, return_embed=return_embed, guild=guild, everything=everything, basic_details=basic_details)

                        return roblox_account, discord_profile.accounts, embed

            options = await get_user_value(user, ["robloxAccounts", {}], "robloxID")
            roblox_accounts = options.get("robloxAccounts") or {}
            accounts = roblox_accounts.get("accounts", [])
            guilds = roblox_accounts.get("guilds", {})

            roblox_account = guild and guilds.get(guild_id) or options.get("robloxID")
            primary_account = options.get("robloxID")

            if roblox_account:
                if not discord_profile:
                    discord_profile = DiscordProfile(user_id)

                    if primary_account:
                        discord_profile.primary_account = RobloxUser(roblox_id=primary_account)

                        if roblox_account != primary_account:
                            embed = await discord_profile.primary_account.sync(return_embed=return_embed, author=author)

                    discord_profile.accounts = accounts

                roblox_user = None

                if cache:
                    roblox_user = await cache_get(f"roblox_users:{roblox_account}")

                roblox_user = roblox_user or RobloxUser(roblox_id=roblox_account)
                embed = await roblox_user.sync(*args, user=user, group_ids=group_ids, author=author, return_embed=return_embed, guild=guild, everything=everything, basic_details=basic_details)

                if guild:
                    discord_profile.guilds[guild_id] = roblox_user

                if cache:
                    await cache_set(f"discord_profiles:{user_id}", discord_profile)
                    await cache_set(f"roblox_users:{roblox_account}", roblox_user)

                return roblox_user, accounts, embed

            else:
                if accounts:
                    return None, accounts, embed
                else:
                    raise UserNotVerified
        else:
            if not (roblox_id or username):
                raise BadUsage("Must supply a username or ID")

            if not roblox_id:
                roblox_id, username = await self.get_roblox_id(username)

            if roblox_id:
                roblox_user = await cache_get(f"roblox_users:{roblox_id}")

                if not roblox_user:
                    roblox_user = RobloxUser(roblox_id=roblox_id)

                    if cache:
                        await cache_set(f"roblox_users:{roblox_id}", roblox_user)

                embed = await roblox_user.sync(*args, user=user, author=author, group_ids=group_ids, guild=guild, return_embed=return_embed, everything=everything, basic_details=basic_details)

                return roblox_user, [], embed

            raise BadUsage("Unable to resolve a user")


    # @staticmethod
    # async def apply_perks(roblox_user, embed, guild=None, groups=False, user=None, tags=False):
    #     if not embed:
    #         return

    #     user_tags = []
    #     user_notable_groups = {}
    #     username_emotes_ = set()
    #     username_emotes = ""

    #     if roblox_user:
    #         if tags:
    #             for special_title, special_group in EMBED_PERKS["GROUPS"].items():
    #                 group = roblox_user.groups.get(special_group[0])

    #                 if group:
    #                     if special_group[1] and ((special_group[1] < 0 and group.user_rank_id < abs(special_group[1])) or (special_group[1] > 0 and group.user_rank_id != special_group[1])):
    #                         continue

    #                     user_tags.append(special_title)

    #                     if special_group[2]:
    #                         if guild:
    #                             if guild.default_role.permissions.external_emojis:
    #                                 username_emotes_.add(special_group[2])
    #                             else:
    #                                 if special_group[3]:
    #                                     username_emotes_.add(special_group[3])
    #                         else:
    #                             username_emotes_.add(special_group[2])

    #         username_emotes = "".join(username_emotes_)

    #         if username_emotes:
    #             for i, field in enumerate(embed.fields):
    #                 if field.name == "Username":
    #                     embed.set_field_at(i, name="Username", value=f"{username_emotes} {field.value}")

    #                     break

    #         if groups:
    #             all_notable_groups = await cache_get("partners:notable_groups", primitives=True, redis_hash=True) or {}
    #             user_notable_groups = {}

    #             for notable_group_id, notable_title in all_notable_groups.items():
    #                 notable_group_id = notable_group_id.decode('utf-8')
    #                 notable_title    = notable_title.decode('utf-8')

    #                 group = roblox_user.groups.get(notable_group_id)

    #                 if group:
    #                     user_notable_groups[group.group_id] = (group, notable_title)

    #     if guild and embed:
    #         cache_partner = await cache_get(f"partners:guilds:{guild.id}", primitives=True, redis_hash=True)
    #         verified_reaction = guild.default_role.permissions.external_emojis and REACTIONS["VERIFIED"] or ":white_check_mark:"

    #         if cache_partner:
    #             embed.description = f"{verified_reaction} This is an **official server** of [{cache_partner.get(b'group_name', 'N/A').decode('utf-8')}](https://www.roblox.com/groups/{cache_partner.get(b'group_id').decode('utf-8')}/-)"
    #             embed.colour = PARTNERED_SERVER

    #     if tags and user:
    #         if await cache_get(f"partners:users:{user.id}", primitives=True):
    #             user_tags.append("Fluxblox Partner")
    #             embed.colour = PARTNERS_COLOR

    #     return user_tags, user_notable_groups


class DiscordProfile:
    __slots__ = ("id", "primary_account", "accounts", "guilds")

    def __init__(self, user_id, **kwargs):
        self.id = user_id

        self.primary_account = kwargs.get("primary_account")
        self.accounts = kwargs.get("accounts", [])
        self.guilds = kwargs.get("guilds", {})

    def __eq__(self, other):
        return self.id == getattr(other, "id", None)

class Group(Bloxlink.Module):
    __slots__ = ("name", "group_id", "description", "rolesets", "owner", "member_count",
                 "emblem_url", "url", "user_rank_name", "user_rank_id", "shout")

    def __init__(self, group_id, group_data, my_roles=None):
        numeric_filter = filter(str.isdigit, str(group_id))
        self.group_id = "".join(numeric_filter)

        self.name = None
        self.description = None
        self.owner = None
        self.member_count = None
        self.emblem_url = None
        self.rolesets = {}
        self.url = f"https://www.roblox.com/groups/{self.group_id}"
        self.shout = None

        self.user_rank_name = None
        self.user_rank_id = None

        self.load_json(group_data, my_roles=my_roles)

    async def apply_rolesets(self):
        if self.rolesets:
            return

        group_data, roleset_response = await fetch(f"{GROUP_API}/v1/groups/{self.group_id}/roles", json=True)

        if roleset_response.status == 200:
            self.load_json(group_data)

        elif roleset_response.status >= 500:
            raise RobloxDown

    def load_json(self, group_data, my_roles=None):
        self.shout = group_data.get("shout") or self.shout
        self.emblem_url = self.emblem_url or group_data.get("imageUrl")

        self.name = self.name or group_data.get("name") or group_data.get("Name", "")
        self.member_count = self.member_count or group_data.get("memberCount", 0)
        self.description = self.description or group_data.get("description") or group_data.get("Description", "")

        self.user_rank_name = self.user_rank_name or (my_roles and my_roles.get("name", "").strip())
        self.user_rank_id = self.user_rank_id or (my_roles and my_roles.get("rank"))

        self.owner = self.owner or group_data.get("owner")

        if not self.rolesets and (group_data.get("roles") or group_data.get("Roles")):
            rolesets = group_data.get("roles") or group_data.get("Roles")

            for roleset in reversed(rolesets):
                roleset_id = roleset.get("rank") or roleset.get("Rank")
                roleset_name = roleset.get("name").strip()

                if roleset_id:
                    self.rolesets[roleset_name.lower()] = [roleset_name, int(roleset_id)]

    def __str__(self):
        return f"Group ({self.name or self.group_id})"

    def __repr__(self):
        return self.__str__()

class RobloxItem:
    __slots__ = ("item_id", "name", "description", "url", "owner", "created")

    def __init__(self, item_id, item_data):
        self.item_id = str(item_id)
        self.name = None
        self.description = None
        self.owner = None
        self.url = None
        self.created = None

        self.load_json(item_data)

    def load_json(self, item_data):
        self.name = self.name or item_data.get("Name")
        self.description = self.description or item_data.get("Description")
        self.owner = self.owner or item_data.get("Creator")
        self.created = self.created or item_data.get("Created")
        self.url = self.url or f"https://www.roblox.com/catalog/{self.item_id}/-"


class Game(RobloxItem):
    def __init__(self, game_id, game_data):
        super().__init__(game_id, game_data)

        self.url = f"https://www.roblox.com/games/{self.item_id}/-"
        self.group_game = False
        self.creator_name = ""
        self.up_votes = 0
        self.down_votes = 0
        self.player_count = 0

        #self.load_json(game_data)
    """
    def load_json(self, data):
        self.group_game   = data.get("creatorType") == "Group"
        self.up_votes     = self.up_votes or data.get("totalUpVotes")
        self.down_votes   = self.down_votes or data.get("totalDownVotes")
        self.player_count = self.player_count or data.get("playerCount")
    """


    def __str__(self):
        return f"Game ({self.name or self.item_id})"

    def __repr__(self):
        return self.__str__()


class RobloxUser(Bloxlink.Module):
    __slots__ = ("username", "id", "discord_id", "verified", "complete", "more_details", "groups",
                 "avatar", "premium", "presence", "badges", "description", "banned", "age", "created",
                 "join_date", "profile_link", "session", "embed", "dev_forum", "display_name", "full_join_string",
                 "group_ranks", "overlay", "age_string", "flags")

    def __init__(self, *, username=None, roblox_id=None, discord_id=None, **kwargs):
        self.username = username
        self.id = roblox_id
        self.discord_id = discord_id

        self.verified = False
        self.complete = False
        self.more_details = False
        self.partial = False

        self.groups = kwargs.get("groups", {})
        self.avatar = kwargs.get("avatar")
        self.premium = kwargs.get("premium", False)
        self.presence = kwargs.get("presence")
        self.badges = kwargs.get("badges", [])
        self.description = kwargs.get("description", "")
        self.banned = kwargs.get("banned", False)
        self.created =  kwargs.get("created", None)
        self.dev_forum =  kwargs.get("dev_forum", None)
        self.display_name =  kwargs.get("display_name", username)
        self.group_ranks = kwargs.get("group_ranks", {})
        self.overlay = kwargs.get("overlay", "")

        self.name = username # TEMP TO MAKE IT COMPATIBLE WITH NEW ROBLOXUSERS
        self.flags = 0

        self.embed = None

        self.age = 0
        self.join_date = None
        self.full_join_string = None
        self.age_string = None
        self.profile_link = roblox_id and f"https://www.roblox.com/users/{roblox_id}/profile"

    @staticmethod
    async def get_details(*args, user=None, author=None, username=None, roblox_id=None, everything=False, basic_details=False, roblox_user=None, group_ids=None, guild=None, return_embed=False):
        if everything:
            basic_details = True

        roblox_data = {
            "username": username,
            "name": username,
            "display_name": None,
            "id": roblox_id,
            "groups": None,
            "group_ranks": {},
            "presence": None,
            "premium": None,
            "badges": None,
            "avatar": None,
            "profile_link": roblox_id and f"https://www.roblox.com/users/{roblox_id}/profile",
            "banned": None,
            "description": None,
            "age": None,
            "join_date": None,
            "full_join_string": None,
            "age_string": None,
            "created": None,
            "dev_forum": None,
            "flags": 0,
            "overlay": ""
        }

        if group_ids:
            group_ids[0].update(group_ids[1].get("groups", {}.keys()))
            group_ids = group_ids[0]

        roblox_user_from_cache = None
        embed = discord.Embed()
        files = []
        view = discord.ui.View()
        card = None

        if username:
            cache_find = await cache_get(f"usernames_to_ids:{username}")

            if cache_find:
                roblox_id, username = cache_find

            if roblox_id:
                roblox_user_from_cache = await cache_get(f"roblox_users:{roblox_id}")

        if roblox_user_from_cache and roblox_user_from_cache.verified:
            roblox_data["id"] = roblox_id or roblox_user_from_cache.id
            roblox_data["username"] = username or roblox_user_from_cache.username
            roblox_data["name"] = username or roblox_user_from_cache.name
            roblox_data["display_name"] = roblox_user_from_cache.display_name
            roblox_data["groups"] = roblox_user_from_cache.groups
            roblox_data["group_ranks"] = roblox_user_from_cache.group_ranks
            roblox_data["avatar"] = roblox_user_from_cache.avatar
            roblox_data["premium"] = roblox_user_from_cache.premium
            roblox_data["presence"] = roblox_user_from_cache.presence
            roblox_data["badges"] = roblox_user_from_cache.badges
            roblox_data["banned"] = roblox_user_from_cache.banned
            roblox_data["join_date"] = roblox_user_from_cache.join_date
            roblox_data["age_string"] = roblox_user_from_cache.age_string
            roblox_data["full_join_string"] = roblox_user_from_cache.full_join_string
            roblox_data["description"] = roblox_user_from_cache.description
            roblox_data["age"] = roblox_user_from_cache.age
            roblox_data["created"] = roblox_user_from_cache.created
            roblox_data["dev_forum"] = roblox_user_from_cache.dev_forum
            roblox_data["overlay"] = roblox_user_from_cache.overlay
            roblox_data["flags"] = roblox_user_from_cache.flags


        if roblox_id and not username:
            roblox_id, username = await Roblox.get_roblox_username(roblox_id)
            roblox_data["username"] = username
            roblox_data["name"] = username
            roblox_data["id"] = roblox_id

        elif not roblox_id and username:
            roblox_id, username = await Roblox.get_roblox_id(username)
            roblox_data["username"] = username
            roblox_data["name"] = username
            roblox_data["id"] = roblox_id

        if not (username and roblox_id):
            return None

        card = Card(user, author, view, roblox_data["id"], roblox_data)

        if return_embed:
            if basic_details or "username" in args:
                embed.add_field(name="Username", value=f"[@{username}]({roblox_data['profile_link']})")

            if basic_details or "id" in args:
                embed.add_field(name="ID", value=roblox_id)

        if roblox_user:
            roblox_user.username = username
            roblox_user.name = username
            roblox_user.id = roblox_id

        async def avatar():
            if roblox_data["avatar"] is not None:
                avatar_url = roblox_data["avatar"]
            else:
                try:
                    avatar_url, _ = await fetch(f"{THUMBNAIL_API}/v1/users/avatar-bust?userIds={roblox_data['id']}&size=100x100&format=Png&isCircular=false", json=True)
                    avatar_url = avatar_url.get("data", [])[0].get("imageUrl")
                except RobloxNotFound:
                    avatar_url = None

                if roblox_user:
                    roblox_user.avatar = avatar_url

                roblox_data["avatar"] = avatar_url

            if return_embed:
                embed.set_thumbnail(url=avatar_url)

                if user:
                    embed.set_author(name=str(user), icon_url=user.avatar.url, url=roblox_data.get("profile_link"))

        async def membership_and_badges():
            if roblox_data["premium"] is not None and roblox_data["badges"] is not None:
                premium = roblox_data["premium"]
                badges = roblox_data["badges"]
            else:
                premium = False
                badges = set()

                data, _ = await fetch(f"{BASE_URL}/badges/roblox?userId={roblox_data['id']}", json=True) # FIXME

                for badge in data.get("RobloxBadges", []):
                    badges.add(badge["Name"])

                roblox_data["badges"] = badges
                roblox_data["premium"] = premium

                if roblox_user:
                    roblox_user.badges = badges
                    roblox_user.premium = premium

            if return_embed:
                if premium:
                    #embed[0].add_field(name="Membership", value=membership)
                    #embed[0].title = f"<:robloxpremium:614583826538299394> {embed[0].title}"
                    # TODO
                    pass

                if (everything or "badges" in args) and badges:
                    embed.add_field(name="Badges", value=", ".join(badges))

        async def groups():
            if roblox_data["groups"] is not None:
                groups = roblox_data["groups"]
            else:
                groups = {}
                group_json, _ = await fetch(f"{GROUP_API}/v2/users/{roblox_data['id']}/groups/roles", json=True)

                for group_data in group_json.get("data", []):
                    group_data, my_roles = group_data.get("group"), group_data.get("role")
                    group_id = str(group_data["id"])
                    groups[group_id] = Group(group_id, group_data=group_data, my_roles=my_roles)

                if roblox_user:
                    roblox_user.groups = groups

                roblox_data["groups"] = groups

                if group_ids and groups:
                    for group_id in group_ids:
                        group = groups.get(group_id)

                        if group:
                            roblox_data["group_ranks"][group.name] = group.user_rank_name

                            if roblox_user:
                                roblox_user.group_ranks = roblox_data["group_ranks"]

        async def profile():
            banned = description = age = created = join_date = display_name = full_join_string = age_string = None

            if roblox_data["description"] is not None and roblox_data["age"] is not None and roblox_data["join_date"] is not None and roblox_data["created"] is not None and roblox_data["display_name"] is not None:
                description = roblox_data["description"]
                age = roblox_data["age"]
                join_date = roblox_data["join_date"]
                banned = roblox_data["banned"]
                created = roblox_data["created"]
                display_name = roblox_data["display_name"]
                full_join_string = roblox_data["full_join_string"]
                age_string = roblox_data["age_string"]
            else:
                banned = None
                description = None
                age = None
                created = None
                join_date = None
                display_name = None
                full_join_string = None
                age_string = None

                profile, _ = await fetch(f"https://users.roblox.com/v1/users/{roblox_data['id']}", json=True)

                description = profile.get("description")
                created = profile.get("created")
                banned = profile.get("isBanned")
                display_name = profile.get("displayName")

                roblox_data["description"] = description
                roblox_data["created"] = created
                roblox_data["banned"] = banned
                roblox_data["display_name"] = display_name

            if age is None:
                today = datetime.today()
                roblox_user_age = parser.parse(created).replace(tzinfo=None)
                age = (today - roblox_user_age).days

                join_date = f"{roblox_user_age.month}/{roblox_user_age.day}/{roblox_user_age.year}"

                roblox_data["age"] = age
                roblox_data["join_date"] = join_date

                if age >= 365:
                    years = math.floor(age/365)
                    ending = f"yr{((years > 1 or years == 0) and 's') or ''}"
                    age_string = f"{years} {ending} ago"
                else:
                    ending = f"day{((age > 1 or age == 0) and 's') or ''}"
                    age_string = f"{age} {ending} ago"

                full_join_string = f"{age_string} ({join_date})"
                roblox_data["full_join_string"] = full_join_string
                roblox_data["age_string"] = age_string

            if embed:
                if age and (everything or "age" in args):
                    embed.add_field(name="Account Created", value=roblox_data["full_join_string"])

                if banned and (everything or "banned" in args):
                    if guild and guild.default_role.permissions.external_emojis:
                        embed.description = f"{REACTIONS['BANNED']} This user is _banned._"
                    else:
                        embed.description = ":skull: This user is _banned._"

                    for i, field in enumerate(embed.fields):
                        if field.name == "Username":
                            if guild and guild.default_role.permissions.external_emojis:
                                embed.set_field_at(i, name="Username", value=f"{REACTIONS['BANNED']} ~~{roblox_data['username']}~~")
                            else:
                                embed.set_field_at(i, name="Username", value=f":skull: ~~{roblox_data['username']}~~")

                            break
                else:
                    if "banned" in args:
                        embed.description = "This user is not banned."

                if description and (everything or "description" in args):
                    embed.add_field(name="Description", value=description.replace("\n\n\n", "\n\n")[0:500], inline=False)

            if roblox_user:
                roblox_user.description = description
                roblox_user.age = age
                roblox_user.join_date = join_date
                roblox_user.full_join_string = full_join_string
                roblox_user.age_string = age_string
                roblox_user.created = created
                roblox_user.banned = banned
                roblox_user.display_name = display_name

        async def dev_forum():
            dev_forum_profile = None
            trust_levels = {
                0: "No Access",
                1: "Member",
                2: "Regular",
                3: "Editor",
                4: "Leader"
            }

            if roblox_data["dev_forum"] is not None:
                dev_forum_profile = roblox_data["dev_forum"]
            else:
                try:
                    dev_forum_profile_, http_response = await fetch(f"https://devforum.roblox.com/u/by-external/{roblox_data['id']}.json", json=True, raise_on_failure=False, timeout=5, retry=0)

                    if http_response.status == 200:
                        dev_forum_profile = dev_forum_profile_.get("user")

                        roblox_data["dev_forum"] = dev_forum_profile

                        if roblox_user:
                            roblox_user.dev_forum = roblox_data["dev_forum"]

                except (RobloxDown, RobloxAPIError):
                    pass

            if embed and (everything or "dev_forum" in args or "devforum" in args):
                if dev_forum_profile and dev_forum_profile.get("trust_level"):
                    dev_forum_desc = (f"Trust Level: {trust_levels.get(dev_forum_profile['trust_level'], 'No Access')}\n"
                                     f"""{dev_forum_profile.get('title') and f'Title: {dev_forum_profile["title"]}' or ''}""")
                else:
                    dev_forum_desc = "This user isn't in the DevForums."

                if not args:
                    if dev_forum_profile and dev_forum_profile.get("trust_level"):
                        embed.add_field(name="DevForum", value=dev_forum_desc)
                else:
                    embed.description = dev_forum_desc

        async def overlay():
            if "3587262" in roblox_data["groups"] and roblox_data["groups"]["3587262"].user_rank_id >= 50:
                roblox_data["overlay"] = "staff"
                roblox_data["flags"] = roblox_data["flags"] | BLOXLINK_STAFF

            elif "4199740" in roblox_data["groups"]:
                roblox_data["overlay"] = "star"

            # elif "Administrator" in roblox_data["badges"]:
            #     roblox_data["overlay"] = "rblx_staff"

            if roblox_user:
                roblox_user.overlay = roblox_data["overlay"]
                roblox_user.flags = roblox_data["flags"]

        if basic_details or "avatar" in args:
            await avatar()

        if basic_details or "groups" in args:
            await groups()

        if everything or "description" in args or "blurb" in args or "age" in args or "banned" in args:
            await profile()

        # if everything or "premium" in args or "badges" in args:
        #     await membership_and_badges()

        # if everything or "dev_forum" in args or "devforum" in args:
        #     await dev_forum()

        if everything or "overlay" in args:
            await overlay()

        if embed:
            if everything:
                await card.request_front_card()
            else:
                files = []
                display_name = roblox_data["display_name"]

                if display_name:
                    embed.title = display_name
                else:
                    embed.title = username

            view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Visit Profile", url=roblox_data["profile_link"], emoji="<:profile:927447203029606410>"))

            if roblox_data["dev_forum"] and roblox_data["dev_forum"].get("trust_level"):
                view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Visit DevForum Profile", url=f"https://devforum.roblox.com/u/{roblox_data['dev_forum']['username']}", emoji="<:computer:927447222893805578>"))

            if roblox_data["group_ranks"]:
                card.add_flip_card_button()

        return (embed, files, card)

    async def sync(self, *args, user=None, author=None, basic_details=True, group_ids=None, return_embed=False, guild=None, everything=False):
        embed = discord.Embed()

        try:
            embed = await self.get_details(
                *args,
                username = self.username,
                roblox_id = self.id,
                everything = everything,
                basic_details = basic_details,
                return_embed = return_embed,
                group_ids = group_ids,
                roblox_user = self,
                user = user,
                author = author,
                guild = guild
            )

        except RobloxAPIError:
            traceback.print_exc()
            self.complete = False

            if self.discord_id and self.id:
                # TODO: set username from database
                self.partial = True # only set if there is a db entry for the user with the username
            else:
                raise
        else:
            self.complete = self.complete or everything
            self.verified = True
            self.partial = not everything
            self.profile_link = self.profile_link or f"https://www.roblox.com/users/{self.id}/profile"

        return embed

    def __eq__(self, other):
        return self.id == getattr(other, "id", None) or self.username == getattr(other, "username", None)

    def __str__(self):
        return self.id