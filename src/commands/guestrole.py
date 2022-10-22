import rlcompleter
from resources.structures.Fluxblox import Fluxblox  # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error, RobloxNotFound  # pylint: disable=import-error, no-name-in-module
from resources.constants import NICKNAME_TEMPLATES  # pylint: disable=import-error, no-name-in-module


get_group = Fluxblox.get_module("roblox", attrs=["get_group"])
set_guild_value, get_guild_value = Fluxblox.get_module("cache", attrs=["set_guild_value", "get_guild_value"])


@Fluxblox.command
class GuestRoleCommand(Fluxblox.Module):
    """bind a discord role to non-group members"""

    def __init__(self):
        self.arguments = [
            {
                "prompt": "Please specify the **Group ID** to integrate with. The group ID is the rightmost numbers on your Group URL.",
                "slash_desc": "Please enter your Group ID.",
                "name": "group_id",
                "type": "number",
            },
            {
                "prompt": "Please specify the **role name** to bind non-group members. A role will be created if it doesn't already exist.",
                "slash_desc": "Please choose the role to bind to non-group members.",
                "name": "role",
                "type": "role"
            },
            {
                "prompt": "Should these members be given a nickname different from the server-wide `!nickname`? Please specify a nickname, or "
                          "say `skip` to skip this option and default to the server-wide nickname `!nickname` template.\n\nYou may use these templates:"
                          f"```{NICKNAME_TEMPLATES}```",
                "slash_desc": "Please enter a nickname to give to these members.",
                "slash_optional": True,
                "name": "nickname",
                "type": "string",
                "max": 100,
                "formatting": False
            },
            {
                "prompt": "Should any roles be **removed from the user** if they aren't in the group? You can specify multiple roles.\n\n"
                          "Note that this is an **advanced option**, so you most likely should `skip` this.",
                "slash_desc": "Should any roles be removed from the user?",
                "name": "remove_roles",
                "slash_optional": True,
                "multiple": True,
                "type": "role",
                "max": 10,
                "exceptions": ("skip",),
                "footer": "Say **skip** to skip this option."
            }
        ]

        self.permissions = Fluxblox.Permissions().build("FLUXBLOX_MANAGER")
        self.category = "Binds"
        self.aliases = ["guestbind", "guest-role", "guest-bind"]
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        guild = CommandArgs.guild
        response = CommandArgs.response

        group_id = str(CommandArgs.parsed_args["group_id"])
        role = CommandArgs.parsed_args["role"]
        nickname = CommandArgs.parsed_args["nickname"]
        remove_roles = [str(r.id) for r in CommandArgs.parsed_args["remove_roles"]] if (CommandArgs.parsed_args["remove_roles"] and CommandArgs.parsed_args["remove_roles"] != "skip") else []

        nickname_lower = nickname and nickname.lower()
        role_id = str(role.id)

        try:
            group = await get_group(group_id, full_group=False)
        except RobloxNotFound:
            raise Error(f"A group with ID `{group_id}` does not exist. Please try again.")

        role_binds = await get_guild_value(guild, "roleBinds") or {}

        if isinstance(role_binds, list):
            role_binds = role_binds[0]

        role_binds["groups"] = role_binds.get("groups") or {} # {"groups": {"ranges": {}, "binds": {}}}
        role_binds["groups"][group_id] = role_binds["groups"].get(group_id) or {}
        role_binds["groups"][group_id]["binds"] = role_binds["groups"][group_id].get("binds") or {}

        x = "0"

        rank = role_binds["groups"][group_id].get("binds", {}).get(x, {})

        if not isinstance(rank, dict):
            rank = {"nickname": nickname if nickname and nickname_lower not in ("skip", "done") else None, "roles": [str(rank)], "removeRoles": remove_roles}

            if role_id not in rank["roles"]:
                rank["roles"].append(role_id)
        else:
            if role_id not in rank.get("roles", []):
                rank["roles"] = rank.get("roles") or []
                rank["roles"].append(role_id)

            if nickname and nickname_lower not in ("skip", "done"):
                rank["nickname"] = nickname
            else:
                if not rank.get("nickname"):
                    rank["nickname"] = None

            rank["removeRoles"] = remove_roles

        role_binds["groups"][group_id]["binds"][x] = rank

        await set_guild_value(guild, roleBinds=role_binds)

        await response.success(f"Successfully bound this **Guest Role** to role **{role.name}!**")