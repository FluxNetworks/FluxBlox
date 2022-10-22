from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from resources.constants import DEFAULTS # pylint: disable=import-error, no-name-in-module

import discord

set_guild_value, get_guild_value = Fluxblox.get_module("cache", attrs=["set_guild_value", "get_guild_value"])
VerificationView = Fluxblox.get_module("robloxnew.verifym", attrs=["VerificationView"], name_override="verifym")
has_premium = Fluxblox.get_module("premium", attrs=["has_premium"])


class VerifyChannelModal(discord.ui.Modal, title="Verification Channel"):
    Fluxblox_post = discord.ui.TextInput(label="What would you like Fluxblox to write?",
                                                default=DEFAULTS.get("verifyChannelTextModal"),
                                                style=discord.TextStyle.paragraph,
                                                max_length=2000)

    def __init__(self, *args, **kwargs):
        self.submitted = False
        super().__init__(*args, **kwargs)

    async def on_submit(self, interaction: discord.Interaction):
        self.submitted = True

        await interaction.response.send_message("Processing...", ephemeral=True)

class VerifyChannelCommand(Fluxblox.Module):
    """create a special verification channel"""

    def __init__(self):
        self.permissions = Fluxblox.Permissions().build("FLUXBLOX_MANAGER")
        self.aliases = ["verificationchannel", "verification-channel"]
        self.category = "Administration"
        self.slash_enabled = True
        self.arguments = [
            {
                "prompt": "Do you have an existing verification channel?",
                "type": "channel",
                "name": "existing_channel",
                "optional": True
            }
        ]

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        guild    = CommandArgs.guild

        existing_channel = CommandArgs.parsed_args["existing_channel"]

        is_premium = "premium" in (await has_premium(guild=guild)).features

        welcome_message = await get_guild_value(guild, "welcomeMessage")

        my_permissions = guild.me.guild_permissions

        if not my_permissions.manage_channels or not my_permissions.manage_roles:
            return await response.send("I need both the `Manage Channels` and `Manage Roles` permission for this command.")

        try:
            # discord.py doesn't support deferring then sending a modal so we need to send the modal FIRST then create channels after
            modal = VerifyChannelModal()

            if is_premium:
                modal.add_item(item=discord.ui.TextInput(label="What text do you want for your Verify button?",
                                default="Verify with Fluxblox",
                                style=discord.TextStyle.paragraph,
                                required=False,
                                max_length=80,
                                custom_id="verify_channel_modal:verify_button_label"))

            modal.add_item(item=discord.ui.TextInput(label="Message after someone verifies",
                            default=welcome_message or DEFAULTS.get("welcomeMessage"),
                            style=discord.TextStyle.paragraph,
                            required=False,
                            max_length=2000,
                            custom_id="verify_channel_modal:welcome_message"))

            await response.send_modal(modal)

            if existing_channel:
                verify_category = existing_channel.category
            else:
                verify_category = discord.utils.find(lambda c: c.name == "Verification", guild.categories) or await guild.create_category(name="Verification")

            verify_channel = existing_channel or discord.utils.find(lambda c: c.name in ("verify", "verify-instructions"), guild.text_channels) or await guild.create_text_channel(name="verify", category=verify_category)

            await verify_channel.set_permissions(guild.me, send_messages=True, read_messages=True)

            await modal.wait()

            if not modal.submitted:
                return

            verify_button_text = None

            for child in modal.children:
                if child.custom_id == "verify_channel_modal:verify_button_label":
                    verify_button_text = child.value

            try:
                await verify_channel.send(modal.Fluxblox_post.value.replace("{server-name}", guild.name), view=VerificationView(verify_button_text or "Verify with Fluxblox", modal.Fluxblox_post.value))
            except discord.errors.Forbidden:
                await response.send("I was unable to post in your verification channel. Please make sure I have the correct permissions.")
            else:
                success_text = f"All done! Your new verification channel is {verify_channel.mention}!"

                if not is_premium:
                    success_text += ("\n\n**Pro-tip:** Fluxblox Premium subscribers can "
                                    "[customize the text of the verification button and customize the text that Fluxblox posts!](<https://twitter.com/Fluxblox/status/1521487474949857282>)\n"
                                    f"Subscribe from our [Dashboard!](<https://blox.link/dashboard/guilds/{guild.id}/premium>)")

                await response.send(success_text)

        except discord.errors.Forbidden:
            await response.send("I encountered a permission error. Make sure I have the Manage Channels and Manage Permissions permissions.")
