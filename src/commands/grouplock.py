from resources.structures.Fluxblox import Fluxblox  # pylint: disable=import-error, no-name-in-module
from resources.exceptions import RobloxNotFound, RobloxAPIError, Message, Error  # pylint: disable=import-error, no-name-in-module
from resources.constants import DEFAULTS, ARROW # pylint: disable=import-error, no-name-in-module
from config import REACTIONS # pylint: disable=import-error, no-name-in-module
import discord
import re


post_event = Fluxblox.get_module("utils", attrs=["post_event"])
get_group = Fluxblox.get_module("roblox", attrs=["get_group"])
has_premium = Fluxblox.get_module("premium", attrs=["has_premium"])
set_guild_value, get_guild_value = Fluxblox.get_module("cache", attrs=["set_guild_value", "get_guild_value"])




class GroupLockModal(discord.ui.Modal, title="Group Lock"):
    def __init__(self, *args, **kwargs):
        self.dm_message = None
        super().__init__(*args, **kwargs)

    async def on_submit(self, interaction: discord.Interaction):
        for child in self.children:
            if child.custom_id == "group_lock_modal:dm_message":
                self.dm_message = child.value
                await interaction.response.send_message("Successfully recorded the message from the modal.", ephemeral=True)
                break




@Fluxblox.command
class GroupLockCommand(Fluxblox.Module):
    """lock your server to group members"""


    async def auto_complete_group(self, interaction, command_args, focused_option):
        if not focused_option:
            return

        try:
            group = await get_group(focused_option, full_group=True)
        except (RobloxNotFound, RobloxAPIError):
            return []

        return [
            [f"{group.name} ({group.group_id})", group.group_id]
        ]

    async def auto_complete_roleset(self, interaction, command_args, focused_option):
        if not command_args.get("group"):
            return []

        try:
            group = await get_group(command_args["group"], full_group=True)
        except RobloxNotFound:
            group = None

        if group:
            if focused_option:
                possible_rolesets = focused_option.split(",")
                parsed_rolesets   = []
                all_rolesets = set([r[0] for r in group.rolesets.values()])

                for roleset in possible_rolesets:
                    roleset = roleset.strip()
                    roleset_lower = roleset.lower()

                    if not group.rolesets.get(roleset_lower):
                        return []

                    parsed_rolesets.append(group.rolesets[roleset_lower][1])
                    all_rolesets.difference_update({roleset})

                return [focused_option] + list(all_rolesets)

            else:
                return [
                    g[0] for g in group.rolesets.values()
                ]
        else:
            return [
                "Invalid group."
            ]

    def parse_group_id(self, group):
        if not group.isdigit():
            group_search = self.group_id_regex.search(group)

            if not group_search:
                return None

            group = group_search.group(1)

        return group

    def __init__(self):
        self.permissions = Fluxblox.Permissions().build("FLUXBLOX_MANAGER")
        self.category = "Administration"
        self.aliases = ["group-lock", "serverlock", "server-lock"]
        self.slash_enabled = True
        self.slash_defer = False

        self.group_id_regex = re.compile(r".+ \((.+)\)")

    @Fluxblox.subcommand(arguments=[
        {
            "prompt": "What's the group ID you'd like to add?",
            "name": "group",
            "auto_complete": auto_complete_group,
        },
        {
            "prompt": "What Roleset should be allowed in your server? You can specify multiple.",
            "name": "rolesets",
            "auto_complete": auto_complete_roleset,
            "optional": True,
        },
        {
            "prompt": "Customize the DM message sent to users?",
            "name": "customize_dm",
            "type": "choice",
            "choices": ["Yes, customize the DM message", "No, use the default message"],
            "optional": True,
        },
        {
            "prompt": "What action should be taken to VERIFIED users who aren't in your group?",
            "name": "verified_action",
            "type": "choice",
            "choices": ["Kick & DM them", "DM them"],
            "optional": True,
        },
        {
            "prompt": "What action should be taken to UNVERIFIED users?",
            "name": "unverified_action",
            "type": "choice",
            "choices": ["Kick & DM them", "DM them"],
            "optional": True,
        }
    ])
    async def add(self, CommandArgs):
        """add a group to your group-lock"""

        guild      = CommandArgs.guild
        response   = CommandArgs.response
        group_id   = self.parse_group_id(CommandArgs.parsed_args["group"])
        rolesets   = CommandArgs.parsed_args["rolesets"].split(",") if CommandArgs.parsed_args["rolesets"] else []
        dm_choice  = CommandArgs.parsed_args["customize_dm"]
        verified_action     = "kick" if CommandArgs.parsed_args["verified_action"] != "DM them" else "dm"
        unverified_action   = "kick" if CommandArgs.parsed_args["unverified_action"] != "DM them" else "dm"

        if not group_id:
            raise Error("This group could not be loaded. Make sure you select an option from the dropdown.")

        try:
            group = await get_group(group_id, full_group=True)
        except RobloxNotFound:
            raise RobloxAPIError("This group could not be loaded. Please try again later.")

        group_lock = await get_guild_value(guild, "groupLock") or {}
        parsed_rolesets = []

        existing_entry = group_lock.get(group.group_id) or {}
        dm_message     = existing_entry.get("dmMessage")

        donator_profile = await has_premium(guild=guild)

        if "premium" not in donator_profile.features:
            if len(group_lock) >= 1:
                raise Message("If you would like to add more than **1** group to your Group-Lock, then you need Fluxblox Premium.\n"
                              f"Premium subscribers can lock their server with up to **15 groups**, and Pro subscribers "
                              "can bind an **unlimited number of groups!** Subscribe from our "
                              f"[Dashboard!](<https://blox.link/dashboard/guilds/{guild.id}/premium>)", type="info")
        else:
            if len(group_lock) >= 15 and "pro" not in donator_profile.features:
                raise Message(f"If you would like to add more than 15 groups to your Group-Lock, then you need "
                              f"[Fluxblox Pro!](<https://blox.link/dashboard/guilds/{guild.id}/premium>", type="info")

            if len(group_lock) >= 200:
                raise Message("To prevent abuse, 200 is the max number of groups you can add to your Group-Lock. If you require more, "
                              "then please reach out to us at admin@blox.link.", type="info")

        if verified_action == "kick":
            default_dm = DEFAULTS.get("groupLockKickMessageVerified")
        elif verified_action == "dm":
            default_dm = DEFAULTS.get("groupLockDMMessageVerified")

        for roleset_name in rolesets:
            roleset_name = roleset_name.strip()
            roleset = group.rolesets.get(roleset_name.lower())

            if roleset:
                parsed_rolesets.append(int(roleset[1]))

        if dm_choice == "Yes, customize the DM message":
            modal = GroupLockModal()
            modal.add_item(item=discord.ui.TextInput(label="DM sent to users who aren't in your group",
                            default=dm_message or default_dm,
                            style=discord.TextStyle.paragraph,
                            required=True,
                            max_length=2000,
                            custom_id="group_lock_modal:dm_message"))

            await response.send_modal(modal)
            await modal.wait()

            dm_message = modal.dm_message if modal.dm_message != default_dm else None

        elif dm_choice == "No, use the default message":
            dm_message = None

        group_lock[group.group_id] = {"groupName": group.name, "dmMessage": dm_message, "roleSets": parsed_rolesets, "verifiedAction": verified_action, "unverifiedAction": unverified_action}

        await set_guild_value(guild, groupLock=group_lock)

        await response.success("Successfully saved your **Group-Lock!**")


    @Fluxblox.subcommand(arguments=[
        {
            "prompt": "What's the group ID you'd like to remove?",
            "name": "group",
            "auto_complete": auto_complete_group,
        }
    ])
    async def delete(self, CommandArgs):
        """delete a group from your group-lock"""

        guild      = CommandArgs.guild
        response   = CommandArgs.response
        group_id   = self.parse_group_id(CommandArgs.parsed_args["group"])

        group_lock = await get_guild_value(guild, "groupLock") or {}

        group_lock.pop(group_id, None)

        if not group_id:
            raise Error("This group could not be loaded. Make sure you select an option from the dropdown.")

        await set_guild_value(guild, groupLock=group_lock if group_lock else None)

        await response.success("Successfully **deleted** your group from the Group-Lock!")


    @Fluxblox.subcommand()
    async def view(self, CommandArgs):
        """view your group-lock"""

        guild    = CommandArgs.guild
        response = CommandArgs.response

        group_lock = await get_guild_value(guild, "groupLock") or {}

        if not group_lock:
            raise Message("You have no groups added to your Group-Lock!", type="info")

        embed = discord.Embed(title="Fluxblox Group-Lock")
        embed.set_footer(text="Powered by Fluxblox", icon_url=Fluxblox.user.avatar.url)
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else "")

        for group_id, data in group_lock.items():
            dm_message = data.get("dmMessage") or "(Default DM)"
            dm_message = f"{dm_message[:20]}..." if len(dm_message) >= 20 else dm_message

            embed.add_field(
                name=f"{data['groupName']} ({group_id})",
                value=f"**DM** {ARROW} {dm_message}\n"
                      f"{REACTIONS['DONE']} **{data.get('verifiedAction', 'kick').title()}** Guest **Verified** users\n"
                      f"{REACTIONS['DONE']} **{data.get('unverifiedAction', 'kick').title()}** Guest **Un-Verified** users",
                inline=False)

        await response.send(embed=embed)
