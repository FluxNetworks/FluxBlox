from os import getpid
import json
import uuid
import asyncio
import discord
from ..structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from ..constants import CLUSTER_ID, SHARD_RANGE, STARTED, RELEASE, GREEN_COLOR, PROMPT, PLAYING_STATUS # pylint: disable=import-error, no-name-in-module
from ..exceptions import (FluxbloxBypass, Blacklisted, Blacklisted, PermissionError, # pylint: disable=import-error, no-name-in-module
                         RobloxAPIError, CancelCommand, RobloxDown, Error, UserNotVerified) # pylint: disable=import-error, no-name-in-module
from time import time
from math import floor
from psutil import Process
import async_timeout

eval = Fluxblox.get_module("evalm", attrs="__call__")
post_event, suppress_timeout_errors = Fluxblox.get_module("utils", attrs=["post_event", "suppress_timeout_errors"])
guild_obligations, get_user, get_nickname, format_update_embed = Fluxblox.get_module("roblox", attrs=["guild_obligations", "get_user", "get_nickname", "format_update_embed"])
get_guild_value = Fluxblox.get_module("cache", attrs="get_guild_value")



@Fluxblox.module
class IPC(Fluxblox.Module):
    def __init__(self):
        self.pending_tasks = {}
        self.clusters = set()

    async def handle_message(self, message):
        message = json.loads(str(message["data"], "utf-8"))

        data = message["data"]
        type = message["type"]
        nonce = message["nonce"]
        original_cluster = message.get("original_cluster")
        waiting_for = message.get("waiting_for")
        cluster_id = message.get("cluster_id")
        extras = message.get("extras", {})

        if type == "IDENTIFY":
            # we're syncing this cluster with ourselves, and send back our clusters
            if original_cluster == CLUSTER_ID:
                if isinstance(data, int):
                    self.clusters.add(data)
                else:
                    for x in data:
                        self.clusters.add(x)
            else:
                self.clusters.add(original_cluster)

                response_data = json.dumps({
                    "nonce": None,
                    "cluster_id": CLUSTER_ID,
                    "data": list(self.clusters),
                    "type": "IDENTIFY",
                    "original_cluster": original_cluster,
                    "waiting_for": waiting_for
                })

                await self.redis.publish(f"{RELEASE}:CLUSTER_{original_cluster}", response_data)

        elif type == "ACTION_REQUEST":
            action = data.get("action")
            action_type = data.get("type")
            guild_id = int(data.get("guildID"))

            guild = Fluxblox.get_guild(guild_id)

            if guild:
                response_data = {
                    "nonce": nonce,
                }

                if action == "request":
                    if action_type == "channels":
                        response_data["type"] = "channels"
                        channels_result = []

                        for category, channels in guild.by_category():
                            if category:
                                channels_result.append({
                                    "id": str(category.id),
                                    "name": category.name,
                                    "position": category.position,
                                    "type": category.type,
                                })

                            if channels:
                                channels_result += [
                                    {
                                        "id": str(c.id),
                                        "name": c.name,
                                        "position": c.position,
                                        "type": c.type,
                                    } for c in channels
                                ]

                        response_data["result"] = channels_result
                        response_data["success"] = True

                    elif action_type == "roles":
                        response_data["type"] = "roles"
                        response_data["result"] = [
                            {
                                "id": str(r.id),
                                "name": r.name,
                                "position": r.position,
                                "hoist": r.hoist,
                                "managed": r.managed,
                                "permissions": r.permissions.value,
                                "color": str(r.colour)

                            } for r in guild.roles
                        ]

                        response_data["success"] = True

                    elif action_type == "guild":
                        response_data["type"] = "guild"
                        response_data["result"] = {
                            "id": str(guild.id),
                            "name": guild.name,
                            "icon": str(guild.icon) if guild.icon else None,
                            "owner": str(guild.owner_id),
                            "splash": str(guild.banner) if guild.banner else None,
                            "totalMembers": guild.member_count or 0,
                            "createdDate": guild.created_at.timestamp(),
                        }
                        response_data["success"] = True

                    else:
                        response_data["success"] = False
                        response_data["error"] = "Invalid action type"

                elif action == "create":
                    error = None

                    if action_type == "roles":
                        role_name = data["name"]
                        role = discord.utils.find(lambda r: r.name == role_name.strip(), guild.roles)

                        if not role:
                            try:
                                role = await guild.create_role(name=role_name, reason="Creating role from website")
                            except discord.errors.Forbidden:
                                error = "Insufficient permissions"
                            except discord.errors.HTTPException as e:
                                error = f"HTTP Exception -- {e}"

                        if not error:
                            response_data["result"] = {
                                "id": str(role.id),
                                "name": role.name,
                            }
                            response_data["success"] = True
                        else:
                            response_data["success"] = False
                            response_data["error"] = error

                    elif action_type == "webhooks":
                        channel_id = data["channelID"]
                        webhook_name = data["name"]
                        webhook_avatar = data["avatar"]

                        channel = guild.get_channel(int(channel_id))

                        if channel:
                            try:
                                webhook = await channel.create_webhook(name=webhook_name)
                            except discord.errors.Forbidden:
                                response_data["error"] = "Insufficient permissions"
                                response_data["success"] = False
                            except discord.errors.HTTPException as e:
                                response_data["error"] = f"HTTP Exception -- {e}"
                                response_data["success"] = False
                            else:
                                response_data["result"] = {
                                    "id": str(webhook.id),
                                    "token": webhook.token,
                                    "channelID": str(webhook.channel_id),
                                }
                                response_data["success"] = True
                        else:
                            response_data["error"] = "Channel not found"
                            response_data["success"] = False

                    else:
                        response_data["success"] = False
                        response_data["error"] = "Invalid action type"

                else:
                    response_data["success"] = False
                    response_data["error"] = "Invalid action type"


                await self.redis.publish(nonce, json.dumps(response_data))

        elif type == "VERIFICATION":
            if data.get("guildID"): # ignore verifications by v2
                return

            discord_id = int(data["discordID"])
            guilds = data["guilds"]
            roblox_id = data["robloxID"]

            for guild_id in guilds:
                guild = Fluxblox.get_guild(int(guild_id))

                if guild:
                    member = guild.get_member(discord_id)

                    if not member:
                        try:
                            member = await guild.fetch_member(discord_id)
                        except discord.errors.NotFound:
                            return

                    # if not member:
                    #     return

                    if member.pending or guild.verification_level == discord.VerificationLevel.highest:
                        return

                    try:
                        roblox_user = (await get_user(roblox_id=roblox_id))[0]
                    except RobloxDown:
                        return

                    except RobloxAPIError as e:
                        print(e, flush=True)

                        return

                    try:
                        added, removed, nickname, errors, warnings, roblox_user, _ = await guild_obligations(
                            member,
                            guild                = guild,
                            join                 = True,
                            roles                = True,
                            nickname             = True,
                            roblox_user          = roblox_user,
                            cache                = False,
                            dm                   = False,
                            exceptions           = ("CancelCommand", "UserNotVerified", "Blacklisted", "FluxbloxBypass", "RobloxAPIError", "RobloxDown", "PermissionError"))

                    except (CancelCommand, UserNotVerified, Blacklisted, FluxbloxBypass, RobloxAPIError, RobloxDown, PermissionError):
                        pass

                    else:
                        try:
                            await post_event(guild, "verification", f"{member.mention} has **verified** as `{roblox_user.username}`.", GREEN_COLOR)
                        except Error:
                            pass


        elif type == "EVAL":
            """
            res = (await eval(data, codeblock=False)).description

            data = json.dumps({
                "nonce": nonce,
                "cluster_id": CLUSTER_ID,
                "data": res,
                "type": "CLIENT_RESULT",
                "original_cluster": original_cluster,
                "waiting_for": waiting_for
            })

            await self.redis.publish(f"{RELEASE}:CLUSTER_{original_cluster}", data)
            """
            pass

        elif type == "CLIENT_RESULT":
            task = self.pending_tasks.get(nonce)

            if task:
                task[1][cluster_id] = data
                task[2] += 1
                waiting_for = message["waiting_for"] or len(self.clusters)

                if task[2] == waiting_for:
                    if not task[0].done():
                        task[0].set_result(True)

        elif type == "DM":
            if 0 in SHARD_RANGE:
                try:
                    message_ = await Fluxblox.wait_for("message", check=lambda m: m.author.id == data and not m.guild, timeout=PROMPT["PROMPT_TIMEOUT"])
                except asyncio.TimeoutError:
                    message_ = "cancel (timeout)"

                response_data = json.dumps({
                    "nonce": nonce,
                    "cluster_id": CLUSTER_ID,
                    "data": getattr(message_, "content", message_),
                    "type": "CLIENT_RESULT",
                    "original_cluster": original_cluster,
                    "waiting_for": waiting_for
                })

                await self.redis.publish(f"{RELEASE}:CLUSTER_{original_cluster}", response_data)

        elif type == "DM_AND_INTERACTION":
            if 0 in SHARD_RANGE:
                try:
                    task_1 = asyncio.create_task(suppress_timeout_errors(Fluxblox.wait_for("message", check=lambda m: m.author.id == data and not m.guild, timeout=PROMPT["PROMPT_TIMEOUT"])))
                    task_2 = asyncio.create_task(suppress_timeout_errors(Fluxblox.wait_for("interaction", check=lambda i: i.user.id == data and not i.guild_id and i.data.get("custom_id"), timeout=PROMPT["PROMPT_TIMEOUT"])))

                    result_set, pending = await asyncio.wait({task_1, task_2}, return_when=asyncio.FIRST_COMPLETED, timeout=PROMPT["PROMPT_TIMEOUT"])

                    if result_set:
                        item = next(iter(result_set)).result()

                        if hasattr(item, "content"):
                            message_content = {"type": "message", "content": item.content}
                        else:
                            if item.data["component_type"] == 3:
                                message_content = {"type": "select", "values": item.data["values"]}
                            else:
                                message_content = {"type": "button", "content": item.data["custom_id"]}
                    else:
                        message_content = {"type": "message", "content": "cancel (timeout)"}

                except asyncio.TimeoutError:
                    message_content = {"type": "message", "content": "cancel (timeout)"}

                response_data = json.dumps({
                    "nonce": nonce,
                    "cluster_id": CLUSTER_ID,
                    "data": message_content,
                    "type": "CLIENT_RESULT",
                    "original_cluster": original_cluster,
                    "waiting_for": waiting_for
                })

                await self.redis.publish(f"{RELEASE}:CLUSTER_{original_cluster}", response_data)

        elif type == "STATS":
            seconds = floor(time() - STARTED)

            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            d, h = divmod(h, 24)

            days, hours, minutes, seconds = None, None, None, None

            if d:
                days = f"{d}d"
            if h:
                hours = f"{h}h"
            if m:
                minutes = f"{m}m"
            if s:
                seconds = f"{s}s"

            uptime = f"{days or ''} {hours or ''} {minutes or ''} {seconds or ''}".strip()

            process = Process(getpid())
            mem = floor(process.memory_info()[0] / float(2 ** 20))

            response_data = json.dumps({
                "nonce": nonce,
                "cluster_id": CLUSTER_ID,
                "data": (len(self.client.guilds), mem, uptime),
                "type": "CLIENT_RESULT",
                "original_cluster": original_cluster,
                "waiting_for": waiting_for
            })

            await self.redis.publish(f"{RELEASE}:CLUSTER_{original_cluster}", response_data)

        elif type == "USERS":
            response_data = json.dumps({
                "nonce": nonce,
                "cluster_id": CLUSTER_ID,
                "data": (sum([g.member_count for g in self.client.guilds]), len(self.client.guilds)),
                "type": "CLIENT_RESULT",
                "original_cluster": original_cluster,
                "waiting_for": waiting_for
            })

            await self.redis.publish(f"{RELEASE}:CLUSTER_{original_cluster}", response_data)

        elif type == "PLAYING_STATUS":
            presence_type = extras.get("presence_type", "normal")
            playing_status = extras.get("status", PLAYING_STATUS)

            if presence_type == "normal":
                await Fluxblox.change_presence(status=discord.Status.online, activity=discord.Game(playing_status))

            elif presence_type == "streaming":
                stream_url = extras.get("stream_url", "https://twitch.tv/blox_link")

                await Fluxblox.change_presence(activity=discord.Streaming(name=playing_status, url=stream_url))

            response_data = json.dumps({
                "nonce": nonce,
                "cluster_id": CLUSTER_ID,
                "data": True,
                "type": "CLIENT_RESULT",
                "original_cluster": original_cluster,
                "waiting_for": waiting_for
            })

            await self.redis.publish(f"{RELEASE}:CLUSTER_{original_cluster}", response_data)

    async def __setup__(self):
        REDIS_CHANNELS = [f"{RELEASE}:GLOBAL", f"{RELEASE}:CLUSTER_{CLUSTER_ID}", "VERIFICATION", "ACTION_REQUEST"]

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(*REDIS_CHANNELS)

        response_data = json.dumps({
            "nonce": None,
            "cluster_id": CLUSTER_ID,
            "data": CLUSTER_ID,
            "type": "IDENTIFY",
            "original_cluster": CLUSTER_ID,
            "waiting_for": None
        })

        await self.redis.publish(f"{RELEASE}:GLOBAL", response_data)

        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True)

                if message:
                    self.loop.create_task(self.handle_message(message))

            except self.redis.exceptions.ConnectionError:
                while True:
                    try:
                        await self.redis.ping()
                    except self.redis.exceptions.ConnectionError:
                        await asyncio.sleep(10)
                    else:
                        await pubsub.subscribe(REDIS_CHANNELS)
                        break




    async def broadcast(self, message, type, send_to=f"{RELEASE}:GLOBAL", waiting_for=None, timeout=10, response=True, **kwargs):
        nonce = str(uuid.uuid4())

        if waiting_for and isinstance(waiting_for, str):
            waiting_for = int(waiting_for)

        future = self.loop.create_future()
        self.pending_tasks[nonce] = [future, {x:"cluster timeout" for x in self.clusters}, 0]

        response_data = json.dumps({
            "nonce": response and nonce,
            "data": message,
            "type": type,
            "original_cluster": CLUSTER_ID,
            "cluster_id": CLUSTER_ID,
            "waiting_for": waiting_for,
            "extras": kwargs
        })


        await self.redis.publish(send_to, response_data)

        if response:
            try:
                async with async_timeout.timeout(timeout):
                    await future
            except asyncio.TimeoutError:
                pass

            result = self.pending_tasks[nonce][1]
            self.pending_tasks[nonce] = None

            return result
        else:
            self.pending_tasks[nonce] = None # this is necessary to prevent any race conditions
