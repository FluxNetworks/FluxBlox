from . import Permissions, Fluxblox # pylint: disable=import-error, no-name-in-module
from ..constants import OWNER, RELEASE # pylint: disable=import-error, no-name-in-module
from ..exceptions import PermissionError, Message, CancelCommand # pylint: disable=import-error, no-name-in-module
from inspect import iscoroutinefunction
import discord
import re

has_premium = Fluxblox.get_module("premium", attrs=["has_premium"])
get_guild_value = Fluxblox.get_module("cache", attrs=["get_guild_value"])
has_magic_role = Fluxblox.get_module("extras", attrs=["has_magic_role"])

flag_pattern = re.compile(r"--?(.+?)(?: ([^-]*)|$)")


class Executable:
    def __init__(self, executable):
        self.name = ""
        self.description = executable.__doc__ or "N/A"
        self.full_description = getattr(executable, "full_description", self.description)
        self.permissions = getattr(executable, "permissions", Permissions())
        self.arguments = getattr(executable, "arguments", [])
        self.category = getattr(executable, "category", "Miscellaneous")
        self.examples = getattr(executable, "examples", [])
        self.hidden = getattr(executable, "hidden", self.category == "Developer")
        self.free_to_use = getattr(executable, "free_to_use", False)
        self.addon = getattr(executable, "addon", None) # FIXME
        self.fn = getattr(executable, "__main__", None)
        self.cooldown = getattr(executable, "cooldown", 0)
        self.premium = self.permissions.premium or self.category == "Premium"
        self.developer_only = self.permissions.developer_only or self.category == "Developer" or getattr(executable, "developer_only", False) or getattr(executable, "developer", False)
        self.slash_defer = getattr(executable, "slash_defer", False)
        self.slash_ephemeral = getattr(executable, "slash_ephemeral", False)
        self.slash_args = getattr(executable, "slash_args", None)
        self.slash_guilds = getattr(executable, "slash_guilds", [])
        self.dm_allowed = getattr(executable, "dm_allowed", False)
        self.bypass_channel_perms = getattr(executable, "bypass_channel_perms", False)
        self.aliases = getattr(executable, "aliases", []) # FIXME
        self.premium_bypass_channel_perms = getattr(executable, "premium_bypass_channel_perms", False)
        self.original_executable = executable

        self.usage = []
        command_args = self.arguments

        if command_args:
            for arg in command_args:
                if arg.get("optional"):
                    if arg.get("default"):
                        self.usage.append(f'[{arg.get("name")}={arg.get("default")}]')
                    else:
                        self.usage.append(f'[{arg.get("name")}]')
                else:
                    self.usage.append(f'<{arg.get("name")}>')

        self.usage = " ".join(self.usage) if self.usage else ""

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()

    async def check_permissions(self, author, guild, locale, dm=False, permissions=None, **kwargs):
        permissions = permissions or self.permissions

        if RELEASE != "LOCAL" and author.id == OWNER:
            return True

        if permissions.developer_only or self.developer_only:
            if author.id != OWNER:
                raise PermissionError("This command is reserved for the Fluxblox Developer.")

        if (kwargs.get("premium", self.premium) or permissions.premium) and not kwargs.get("free_to_use", self.free_to_use):
            prem = await has_premium(guild=guild)

            if "premium" not in prem.features:
                raise Message("This command is reserved for Fluxblox Premium subscribers!\n"
                              f"You may subscribe to Fluxblox Premium from our dashboard: <{f'https://blox.link/dashboard/guilds/{guild.id}/premium' if guild else 'https://blox.link/dashboard'}>", type="info")
        try:
            if not dm:
                author_perms = author.guild_permissions

                for role_exception in permissions.exceptions["roles"]:
                    if discord.utils.find(lambda r: r and r.name == role_exception, author.roles):
                        return True

                if permissions.fluxblox_role:
                    role_name = permissions.fluxblox_role

                    magic_roles = await get_guild_value(guild, ["magicRoles", {}])

                    if await has_magic_role(author, guild, "Fluxblox Admin", magic_roles_data=magic_roles):
                        return True
                    else:
                        if role_name == "Fluxblox Manager":
                            if author_perms.manage_guild or author_perms.administrator:
                                pass
                            else:
                                raise PermissionError("You need the `Manage Server` permission to run this command.")

                        elif role_name == "Fluxblox Moderator":
                            if author_perms.kick_members or author_perms.ban_members or author_perms.administrator:
                                pass
                            else:
                                raise PermissionError("You need the `Kick` or `Ban` permission to run this command.")

                        elif role_name == "Fluxblox Updater":
                            if author_perms.manage_guild or author_perms.administrator or author_perms.manage_roles or await has_magic_role(author, guild, "Fluxblox Updater", magic_roles_data=magic_roles):
                                pass
                            else:
                                raise PermissionError("You either need: a role called `Fluxblox Updater`, the `Manage Roles` "
                                                      "role permission, or the `Manage Server` role permission.")

                        elif role_name == "Fluxblox Admin":
                            if author_perms.administrator:
                                pass
                            else:
                                raise PermissionError("You need the `Administrator` role permission to run this command.")

                if permissions.allowed.get("discord_perms"):
                    for perm in permissions.allowed["discord_perms"]:
                        if perm == "Manage Server":
                            if author_perms.manage_guild or author_perms.administrator:
                                pass
                            else:
                                raise PermissionError("You need the `Manage Server` permission to run this command.")
                        else:
                            if not getattr(author_perms, perm, False) and not perm.administrator:
                                raise PermissionError(f"You need the `{perm}` permission to run this command.")


                for role in permissions.allowed["roles"]:
                    if not discord.utils.find(lambda r: r and r.name == role, author.roles):
                        raise PermissionError(f"Missing role: `{role}`")

            if permissions.allowed.get("functions"):
                for function in permissions.allowed["functions"]:

                    if iscoroutinefunction(function):
                        data = [await function(author)]
                    else:
                        data = [function(author)]

                    if not data[0]:
                        raise PermissionError

                    if isinstance(data[0], tuple):
                        if not data[0][0]:
                            raise PermissionError(data[0][1])

        except PermissionError as e:
            if e.message:
                raise e from None

            raise PermissionError("You do not meet the required permissions for this command.")

    @staticmethod
    def parse_flags(content):
        flags = {m.group(1): m.group(2) or True for m in flag_pattern.finditer(content)}

        if flags:
            try:
                content = content[content.index("--"):]
            except ValueError:
                try:
                    content = content[content.index("-"):]
                except ValueError:
                    return {}, ""

        return flags, flags and content or ""


class Command(Executable):
    def __init__(self, command):
        super().__init__(command)

        self.name = command.__class__.__name__[:-7].lower()
        self.subcommands = {}
        self.slash_enabled = getattr(command, "slash_enabled", False)
        self.slash_only = getattr(command, "slash_only", False)
        self.auto_complete = getattr(command, "auto_complete", False)

    async def redirect(self, CommandArgs, new_command_name, *, arguments=None, new_channel=None):
        execute_interaction_command = Fluxblox.get_module("commands", attrs=["execute_interaction_command"])

        try:
            await execute_interaction_command("commands", new_command_name, channel=new_channel or CommandArgs.interaction.channel, response=CommandArgs.response, interaction=CommandArgs.interaction,
                                              subcommand=None, arguments=arguments, command_args=CommandArgs, forwarded=True)
        except CancelCommand:
            pass

class Application(Executable):
    def __init__(self, application):
        super().__init__(application)

        self.type = application.type
        self.name = application.name
        self.slash_enabled = True
