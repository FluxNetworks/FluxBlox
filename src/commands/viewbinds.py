from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from discord import Embed
from resources.exceptions import Message, RobloxNotFound # pylint: disable=import-error, no-name-in-module
from resources.constants import ARROW # pylint: disable=import-error, no-name-in-module

get_binds, get_group, count_binds = Fluxblox.get_module("roblox", attrs=["get_binds", "get_group", "count_binds"])


@Fluxblox.command
class ViewBindsCommand(Fluxblox.Module):
    """view your server bound roles"""

    def __init__(self):
        self.category = "Binds"
        self.aliases = ["binds", "view-binds"]
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        guild = CommandArgs.guild

        role_binds, group_ids = await get_binds(guild)

        if await count_binds(guild) == 0:
            raise Message("You have no bounded roles! Please use `/bind` "
                           "to make a new role bind.", type="silly")

        embed = Embed(title="Fluxblox Role Binds")

        text = []
        if group_ids:
            for group_id, group_data in group_ids.items():
              text.append(f"**Group:** {group_data.get('groupName', '')} ({group_id}) {ARROW} **Nickname:** {group_data['nickname']}")

            text = "\n".join(text)

            embed.add_field(name="Linked Groups", value=text, inline=False)

        if role_binds:
            role_cache = {}

            for category, bind_data in role_binds.items():
                if category == "groups":
                    for group_id, group_data in bind_data.items():
                        text = []
                        for rank_id, rank_data in group_data.get("binds", {}).items():
                            role_names = set()

                            if rank_data.get("roles"):
                                for role_ in rank_data["roles"]:
                                    role_cache_find = role_cache.get(role_)

                                    if role_cache_find:
                                        role_names.add(role_cache_find)
                                    else:
                                        for role in guild.roles:
                                            if role_ in (role.name, str(role.id)):
                                                role_names.add(role.name)
                                                role_cache[role_] = role.name

                                                break
                                        else:
                                            try:
                                                int(role_)
                                            except ValueError:
                                                role_names.add(role_)
                                                role_cache[role_] = role_
                                            else:
                                                # deleted role
                                                # TODO: check if the role is saved in server settings, then delete it
                                                role_names.add("(Deleted Role(s))")
                                                role_cache[role_] = "(Deleted Role(s))"

                                if rank_id in ("guest", "0"):
                                    text.append(f"**Rank:** (Guest Role) {ARROW} **Roles:** {', '.join(role_names)} {ARROW} **Nickname:** {rank_data['nickname']}")
                                else:
                                    text.append(f"**Rank:** {rank_id} {ARROW} **Roles:** {', '.join(role_names)} {ARROW} **Nickname:** {rank_data['nickname']}")
                            else:
                                text.append(f"**Rank:** {rank_id} {ARROW} **Roles:** (Dynamic Roles) {ARROW} **Nickname:** {rank_data['nickname']}")

                        for range_data in group_data.get("ranges", []):
                            role_names = set()

                            if range_data["roles"]:
                                for role_ in range_data["roles"]:
                                    role_cache_find = role_cache.get(role_)

                                    if role_cache_find:
                                        role_names.add(role_cache_find)
                                    else:
                                        for role in guild.roles:
                                            if role_ in (role.name, str(role.id)):
                                                role_names.add(role.name)
                                                role_cache[role_] = role.name

                                                break
                                        else:
                                            try:
                                                int(role_)
                                            except ValueError:
                                                role_names.add(role_)
                                                role_cache[role_] = role_
                                            else:
                                                # deleted role
                                                # TODO: check if the role is saved in server settings, then delete it
                                                role_names.add("(Deleted Role(s))")
                                                role_cache[role_] = "(Deleted Role(s))"

                                text.append(f"**Rank Range:** {range_data['low']} - {range_data['high']} {ARROW} **Roles:** {', '.join(role_names)} {ARROW} **Nickname:** {range_data['nickname']}")
                            else:
                                text.append(f"**Rank Range:** {range_data['low']} - {range_data['high']} {ARROW} **Roles:** (Dynamic Roles) {ARROW} **Nickname:** {range_data['nickname']}")

                        if text:
                            text = "\n".join(text)

                            try:
                                group_name = group_data.get("groupName") or (await get_group(group_id, full_group=True)).name
                            except RobloxNotFound:
                                # TODO: remove group
                                pass
                            else:
                                embed.add_field(name=f"{group_name} ({group_id})", value=text, inline=False)

                else:
                    text = []

                    if category == "gamePasses":
                        category_non_plural = "gamePass"
                        category_non_plural_title = "GamePass"
                        category_title = "GamePasses"
                    elif category == "devForum":
                        category_title = "DevForum Members"
                    elif category == "robloxStaff":
                        category_title = "Roblox Staff"
                    else:
                        category_non_plural = category[:-1]
                        category_non_plural_title = category_non_plural.title()
                        category_title = category.title()

                    if category in ("devForum", "robloxStaff"):
                        role_names = set()

                        if bind_data["roles"]:
                            for role_ in bind_data["roles"]:
                                role_cache_find = role_cache.get(role_)

                                if role_cache_find:
                                    role_names.add(role_cache_find)
                                else:
                                    for role in guild.roles:
                                        if role_ in (role.name, str(role.id)):
                                            role_names.add(role.name)
                                            role_cache[role_] = role.name

                                            break
                                    else:
                                        try:
                                            int(role_)
                                        except ValueError:
                                            role_names.add(role_)
                                            role_cache[role_] = role_
                                        else:
                                            # deleted role
                                            # TODO: check if the role is saved in server settings, then delete it
                                            role_names.add("(Deleted Role(s))")
                                            role_cache[role_] = "(Deleted Role(s))"

                            text.append(f"**Roles:** {', '.join(role_names)} {ARROW} **Nickname:** {bind_data['nickname']}")

                        else:
                            text.append(f"**Roles:** (No Roles) {ARROW} **Nickname:** {bind_data['nickname']}")
                    else:
                        for bind_id, bind_vg_data in bind_data.items():
                            display_name = bind_vg_data.get("displayName") or "(No Name)"
                            role_names = set()

                            if bind_vg_data["roles"]:
                                for role_ in bind_vg_data["roles"]:
                                    role_cache_find = role_cache.get(role_)

                                    if role_cache_find:
                                        role_names.add(role_cache_find)
                                    else:
                                        for role in guild.roles:
                                            if role_ in (role.name, str(role.id)):
                                                role_names.add(role.name)
                                                role_cache[role_] = role.name

                                                break
                                        else:
                                            try:
                                                int(role_)
                                            except ValueError:
                                                role_names.add(role_)
                                                role_cache[role_] = role_
                                            else:
                                                # deleted role
                                                # TODO: check if the role is saved in server settings, then delete it
                                                role_names.add("(Deleted Role(s))")
                                                role_cache[role_] = "(Deleted Role(s))"

                                text.append(f"**{category_non_plural_title}:** {display_name} ({bind_id}) {ARROW} **Roles:** {', '.join(role_names)} {ARROW} **Nickname:** {bind_vg_data['nickname']}")

                            else:
                                text.append(f"**{category_non_plural_title}:** {display_name} ({bind_id}) {ARROW} **Roles:** (No Roles) {ARROW} **Nickname:** {bind_vg_data['nickname']}")


                    if text:
                        text = "\n".join(text)
                        embed.add_field(name=category_title, value=text, inline=False)



        embed.set_author(name="Powered by Fluxblox", icon_url=Fluxblox.user.avatar.url)
        embed.set_footer(text="Use /bind to make a new bind, or /unbind to delete a bind")

        await CommandArgs.response.send(embed=embed)
