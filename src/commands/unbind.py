from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
import discord
from resources.exceptions import Error, Message # pylint: disable=import-error, no-name-in-module
from resources.constants import BLURPLE_COLOR # pylint: disable=import-error, no-name-in-module

get_binds, get_group, count_binds = Fluxblox.get_module("roblox", attrs=["get_binds", "get_group", "count_binds"])
post_event = Fluxblox.get_module("utils", attrs=["post_event"])
set_guild_value, get_guild_value = Fluxblox.get_module("cache", attrs=["set_guild_value", "get_guild_value"])


BIND_TYPES = ("asset", "badge", "gamepass")


@Fluxblox.command
class UnBindCommand(Fluxblox.Module):
    """delete a role bind from your server"""

    def __init__(self):
        self.arguments = [{
                "prompt": "Please choose the type of bind to delete.",
                "components": [discord.ui.Select(max_values=1, options=[
                    discord.SelectOption(label="Group", description="Remove a Group bind."),
                    discord.SelectOption(label="Asset", description="Remove a Catalog Asset bind."),
                    discord.SelectOption(label="Badge", description="Remove a Badge bind."),
                    discord.SelectOption(label="GamePass", description="Remove a GamePass bind."),
                    discord.SelectOption(label="DevForum Members", description="Remove a DevForum bind."),
                    discord.SelectOption(label="Roblox Staff", description="Remove a Roblox Staff bind."),
                ])],
                "type": "choice",
                "choices": ("group", "asset", "badge", "gamepass", "devforum members", "roblox staff"),
                "name": "bind_category"
            },
            {
                "prompt": "Please specify the **{bind_category[0]} ID** to delete.",
                "type": "number",
                "name": "bind_id",
                "show_if": lambda c: c["bind_category"][0] not in ("roblox staff", "devforum members")
            }
        ]

        self.permissions = Fluxblox.Permissions().build("FLUXBLOX_MANAGER")
        self.category = "Binds"
        self.aliases = ["delbind", "delbinds", "un-bind", "del-bind"]
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        guild = CommandArgs.guild
        author = CommandArgs.author
        response = CommandArgs.response

        role_binds, group_ids = await get_binds(guild)

        group_ids = await get_guild_value(guild, "groupIDs") or {}

        removed_main_group = False

        if await count_binds(guild) == 0:
            raise Message("You have no bounded roles! Please use `/bind` "
                          "to make a new role bind.", type="info")

        bind_category = CommandArgs.parsed_args["bind_category"][0]
        bind_id = str(CommandArgs.parsed_args["bind_id"]) if CommandArgs.parsed_args["bind_id"] else None

        print(role_binds, group_ids)

        if bind_category == "group":
            found_linked_group = group_ids.get(bind_id)
            found_group = role_binds.get("groups", {}).get(bind_id) or {}

            if not (found_linked_group or found_group):
                raise Message("There's no linked group with this ID!", type="info")

            if found_linked_group:
                parsed_args = await CommandArgs.prompt([{
                    "prompt": "This group is linked as a Main Group. This means anyone who joins from this group will get their role(s), "
                              "and the roles HAVE to match with the Rolesets. Would you like to remove this entry?",
                    "type": "choice",
                    "components": [discord.ui.Select(max_values=1, options=[
                            discord.SelectOption(label="Yes", description="Remove this linked group."),
                            discord.SelectOption(label="No", description="Don't remove this linked group."),
                        ])],
                    "choices": ["yes", "no"],
                    "name": "main_group_choice"
                }])

                if parsed_args["main_group_choice"][0] == "yes":
                    if found_linked_group:
                        del group_ids[bind_id]

                        await set_guild_value(guild, groupIDs=group_ids)

                        if found_group:
                            await response.send("Successfully removed this linked group. There are additional binds that exist that you may remove, however. If you **don't** want to remove the binds, say `cancel`.")
                        else:
                            await response.send("Successfully removed this linked group. There are no additional binds found for this group.")

                    removed_main_group = True

            if found_group:
                parsed_args = await CommandArgs.prompt([
                    {
                        "prompt": f"Please specify the `rank ID` (found on /viewbinds), or say `everything` "
                                  f"to delete all binds for group **{bind_id}**. If this is a _range_, then say the low and high value as: `low-high`. If this is a guest role, say `guest`.",
                        "name": "rank_id"
                    }
                ])

                rank_id = parsed_args["rank_id"].lower()

                if rank_id == "everything":
                    if found_group:
                        binds = found_group.get("binds", {})
                        del role_binds["groups"][bind_id]

                elif "-" in rank_id and not rank_id.lstrip("-").isdigit():
                    rank_id = rank_id.split("-")

                    if len(rank_id) == 2:
                        low, high = rank_id[0].strip(), rank_id[1].strip()

                        if not all(x.isdigit() for x in (high, low)):
                            raise Error("Ranges must have valid integers! An example would be `1-100`.")

                        ranges = found_group.get("ranges", [])

                        for range_ in ranges:
                            if int(low) == range_["low"] and int(high) == range_["high"]:

                                for range__ in found_group.get("ranges", []):
                                    if int(low) == range__["low"] and int(high) == range__["high"]:
                                        found_group["ranges"].remove(range__)
                                        role_binds["groups"][bind_id]["ranges"] = found_group["ranges"]
                                        break

                                break
                        else:
                            raise Message("There's no range found with this ID!", type="info")

                else:
                    found_group["binds"] = found_group.get("binds") or {}

                    if rank_id in ("guest", "guest."):
                        if found_group["binds"].get("guest"):
                            rank_id = "guest"
                        elif found_group["binds"].get("0"):
                            rank_id = "0"

                    binds_trello = found_group["binds"].get(rank_id)
                    binds = found_group.get("binds", {})

                    if binds_trello:
                        if binds.get(rank_id):
                            del binds[rank_id]

                        if not (found_group.get("binds", {}) or found_group.get("ranges", {})):
                            role_binds["groups"].pop(bind_id, None)

                    else:
                        raise Error(f"No matching bind found for group `{bind_id}` with rank `{rank_id}`!")

            else:
                if not removed_main_group:
                    raise Error(f"No matching bind found for group `{bind_id}`!")

            await set_guild_value(guild, roleBinds=role_binds, groupIDs=group_ids)

            await post_event(guild, "bind", f"{author.mention} ({author.id}) has **removed** some `binds`.", BLURPLE_COLOR)

            raise Message("All bind removals were successful.", type="success")

        else:
            if bind_category == "gamepass":
                bind_category_internal = "gamePasses"
            elif bind_category == "devforum members":
                bind_category_internal = "devForum"
            elif bind_category == "roblox staff":
                bind_category_internal = "robloxStaff"
            else:
                bind_category_internal = f"{bind_category}s"

            all_binds = role_binds.get(bind_category_internal, {})
            saving_binds = role_binds.get(bind_category_internal)

            if bind_id:
                if not all_binds.get(bind_id):
                    raise Error(f"This `{bind_category}` bind is not bounded!")

                if saving_binds:
                    saving_binds.pop(bind_id, None)

                    if not saving_binds:
                        role_binds.pop(bind_category_internal, None)

                    await set_guild_value(guild, roleBinds=role_binds)

            else:
                if not all_binds:
                    raise Error(f"This `{bind_category}` bind is not bounded!")

                role_binds.pop(bind_category_internal, None)

                await set_guild_value(guild, roleBinds=role_binds)

        await post_event(guild, "bind", f"{author.mention} ({author.id}) has **removed** some `binds`.", BLURPLE_COLOR)

        raise Message("All bind removals were successful.", type="success")
