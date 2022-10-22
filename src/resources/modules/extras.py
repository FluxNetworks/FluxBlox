from ..structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from ..constants import MAGIC_ROLES # pylint: disable=import-error, no-name-in-module


get_guild_value = Fluxblox.get_module("cache", attrs=["get_guild_value"])


@Fluxblox.module
class Extras(Fluxblox.Module):
    def __init__(self):
        pass

    async def has_magic_role(self, author, guild, magic_role_name=None, magic_roles_data=None):
        has_any_magic_role = False
        magic_roles = magic_roles_data or await get_guild_value(guild, "magicRoles") or {}

        for role in author.roles:
            if role and role.name == magic_role_name: # discord.py giving me None for roles...
                has_any_magic_role = True
                return True
            else:
                if role.name in MAGIC_ROLES:
                    has_any_magic_role = True

        users_magic_roles = filter(lambda rd: author.get_role(int(rd[0]) if rd[0] != "undefined" else 0), magic_roles.items())

        if not magic_role_name:
            return bool(users_magic_roles) or has_any_magic_role

        for magic_role in users_magic_roles:
            if magic_role_name in magic_role[1]:
                return True
