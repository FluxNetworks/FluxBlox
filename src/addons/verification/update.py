from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error, UserNotVerified, Message, FluxbloxBypass, CancelCommand, PermissionError, Blacklisted # pylint: disable=import-error, no-name-in-module
from config import REACTIONS # pylint: disable=import-error, no-name-in-module
from resources.constants import RELEASE # pylint: disable=import-error, no-name-in-module
from discord import User
from discord.errors import NotFound
import math

guild_obligations, format_update_embed = Fluxblox.get_module("roblox", attrs=["guild_obligations", "format_update_embed"])
has_premium = Fluxblox.get_module("premium", attrs="has_premium")


class UpdateCommand(Fluxblox.Module):
    """force update user(s) with roles and nicknames"""

    def __init__(self):
        permissions = Fluxblox.Permissions().build("FLUXBLOX_UPDATER")
        permissions.allow_bypass = True

        self.permissions = permissions
        self.aliases = ["update", "updateroles", "update-user"]
        self.arguments = [
            {
                "prompt": "Please select the user to update.",
                "name": "user",
                "type": "user",
                "optional": True
            },
            {
                "prompt": "Please select the role of members to update.",
                "name": "role",
                "type": "role",
                "optional": True
            }
        ]
        self.category = "Administration"
        self.cooldown = 2
        self.REDIS_COOLDOWN_KEY = "guild_scan:{id}"
        self.slash_enabled = True
        self.slash_defer = True
        self.slash_only = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        command  = CommandArgs.command

        user_slash = CommandArgs.parsed_args.get("user")
        role_slash = CommandArgs.parsed_args.get("role")
        users_ = CommandArgs.parsed_args.get("users") or ([user_slash, role_slash] if user_slash or role_slash else None)

        author = CommandArgs.author
        guild = CommandArgs.guild

        users = []

        if not (users_ and CommandArgs.has_permission):
            if not users_:
                await command.redirect(CommandArgs, "getrole")
                raise CancelCommand
            else:
                raise Message("You do not have permission to update users; you need the `Manage Roles` permission, or "
                              "a role called `Fluxblox Updater`.", type="info", hidden=True)

        if not guild.chunked:
            await guild.chunk()

        if users_[1]:
            role = users_[1]

            users += role.members

            if not users:
                raise Error("This role has no members in it!", hidden=True)

        if users_[0]:
            user = users_[0]
            users.append(user)

        len_users = len(users)

        for i, user in enumerate(users):
            if isinstance(user, User):
                try:
                    user = await guild.fetch_member(user.id)
                except NotFound:
                    raise Error("This user isn't in your server!")
                else:
                    users[i] = user

        if self.redis:
            redis_cooldown_key = self.REDIS_COOLDOWN_KEY.format(release=RELEASE, id=guild.id)
            on_cooldown = await self.redis.get(redis_cooldown_key)

            if len_users > 3 and on_cooldown:
                cooldown_time = math.ceil(await self.redis.ttl(redis_cooldown_key)/60)

                if not cooldown_time or cooldown_time == -1:
                    await self.redis.delete(redis_cooldown_key)
                    on_cooldown = None

                if on_cooldown:
                    if on_cooldown == 1:
                        raise Message(f"This server is still queued.")
                    elif on_cooldown == 2:
                        raise Message("This server's scan is currently running.")
                    elif on_cooldown == 3:
                        cooldown_time = math.ceil(await self.redis.ttl(redis_cooldown_key)/60)

                        raise Message(f"This server has an ongoing cooldown! You must wait **{cooldown_time}** more minutes.")

            donator_profile = await has_premium(guild=guild)
            premium = "premium" in donator_profile.features

            if not premium:
                donator_profile = await has_premium(user=author)
                premium = "premium" in donator_profile.features

            cooldown = 0

            if len_users > 10:
                if not premium:
                    raise Error("You need premium in order to update more than 10 members at a time! "
                                f"Use `/donate` for instructions on donating.")

                if len_users >= 100:
                    cooldown = math.ceil(((len_users / 1000) * 120) * 60)
                else:
                    cooldown = 120

                if self.redis:
                    await self.redis.set(redis_cooldown_key, 2, ex=86400)

            #async with response.loading():
            if len_users > 1:
                await response.send(f"Updating **{len_users}** users...")

                for user in users:
                    if not user.bot:
                        try:
                            added, removed, nickname, errors, warnings, roblox_user, _ = await guild_obligations(
                                user,
                                guild             = guild,
                                roles             = True,
                                nickname          = True,
                                dm                = False,
                                exceptions        = ("FluxbloxBypass", "UserNotVerified", "Blacklisted", "PermissionError", "RobloxDown"),
                                cache             = False)
                        except FluxbloxBypass:
                            if len_users <= 10:
                                await response.info(f"{user.mention} **bypassed**")
                        except UserNotVerified:
                            if len_users <= 10:
                                await response.send(f"{REACTIONS['ERROR']} {user.mention} is **not linked to Fluxblox**")
                        except PermissionError as e:
                            raise Error(e.message)
                        except Blacklisted as b:
                            if len_users <= 10:
                                await response.send(f"{REACTIONS['ERROR']} {user.mention} has an active restriction.")
                        except CancelCommand:
                            pass
                        else:
                            if len_users <= 10:
                                await response.send(f"{REACTIONS['DONE']} **Updated** {user.mention}")
            else:
                user = users[0]

                if user.bot:
                    raise Message("Bots can't have Roblox accounts!", type="silly")

                old_nickname = user.display_name

                try:
                    added, removed, nickname, errors, warnings, roblox_user, bind_explanations = await guild_obligations(
                        user,
                        guild             = guild,
                        roles             = True,
                        nickname          = True,
                        cache             = False,
                        dm                = False,
                        event             = True,
                        exceptions        = ("FluxbloxBypass", "Blacklisted", "CancelCommand", "UserNotVerified", "PermissionError", "RobloxDown", "RobloxAPIError"))

                    _, card, embed, view = await format_update_embed(
                        roblox_user, user,
                        added=added, removed=removed, errors=errors, warnings=warnings, nickname=nickname if old_nickname != nickname else None,
                        author = author,
                        guild = guild,
                        bind_explanations=bind_explanations
                    )

                    message = await response.send(embed=embed, files=[card.front_card_file] if card else None, view=card.view if card else view)

                    if card:
                        card.response = response
                        card.message = message
                        card.view.message = message

                except FluxbloxBypass:
                    raise Message("Since this user has the Fluxblox Bypass role, I was unable to update their roles/nickname.", type="info")

                except Blacklisted as b:
                    if b.guild_restriction:
                        raise Message(f"This user is server-restricted from using Fluxblox for: `{b.message}`. This is NOT a Fluxblox blacklist.")
                    else:
                        raise Message(f"This user is blacklisted from using Fluxblox for: `{b.message}`.")

                except CancelCommand:
                    pass

                except UserNotVerified:
                    raise Error("This user is not linked to Fluxblox.")

                except PermissionError as e:
                    raise Error(e.message)

            if cooldown:
                await self.redis.set(redis_cooldown_key, 3, ex=cooldown)

            if len_users > 10:
                await response.success("All users updated.")
