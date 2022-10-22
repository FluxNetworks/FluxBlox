from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.constants import NICKNAME_TEMPLATES, DEFAULTS, UNVERIFIED_TEMPLATES, BROWN_COLOR # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.exceptions import Message # pylint: disable=import-error, no-name-in-module, no-name-in-module


post_event = Fluxblox.get_module("utils", attrs=["post_event"])
set_guild_value, get_guild_value = Fluxblox.get_module("cache", attrs=["set_guild_value", "get_guild_value"])


@Fluxblox.command
class JoinDMCommand(Fluxblox.Module):
    """greets people who join the server. by default, this is ENABLED for verified members."""

    def __init__(self):
        self.permissions = Fluxblox.Permissions().build("FLUXBLOX_MANAGER")
        self.category = "Administration"
        self.arguments = [{
            "prompt": "Would you like to alter/disable the DM messages for **verified** or **unverified** users?",
            "type": "choice",
            "choices": ("verified", "unverified"),
            "name": "subcommand"
        }]
        self.hidden = True
        self.aliases = ["join-dm"]

    async def __main__(self, CommandArgs):
        subcommand = CommandArgs.parsed_args["subcommand"]
        if subcommand == "verified":
            await self.verified(CommandArgs)
        elif subcommand == "unverified":
            await self.unverified(CommandArgs)

    @Fluxblox.subcommand()
    async def verified(self, CommandArgs):
        """set the DM message of people who are VERIFIED on Fluxblox"""

        author = CommandArgs.author
        guild = CommandArgs.guild

        verified_DM = await get_guild_value(guild, ["verifiedDM", DEFAULTS.get("welcomeMessage")])

        response = CommandArgs.response

        if verified_DM:
            response.delete(await response.send("When people join your server and are **VERIFIED** on Fluxblox, they will "
                                               f"receive this DM:"))
            response.delete(await response.send(f"```{verified_DM}```"))

        parsed_args_1 = (await CommandArgs.prompt([{
            "prompt": "Would you like to **change** the DM people get when they join and are verified, or "
                        "would you like to **disable** this feature?\n\nPlease specify: (change, disable)",
            "name": "option",
            "type": "choice",
            "choices": ("change", "disable")
        }]))["option"]

        if parsed_args_1 == "change":
            parsed_args_2 = (await CommandArgs.prompt([{
                "prompt": "What would you like the text of the Verified Join DM to be? You may use "
                            f"these templates: ```{NICKNAME_TEMPLATES}```",
                "name": "text",
                "formatting": False
            }], last=True))["text"]

            await set_guild_value(guild, verifiedDM=parsed_args_2)

        elif parsed_args_1 == "disable":
            await set_guild_value(guild, verifiedDM=None)

        await post_event(guild, "configuration", f"{author.mention} ({author.id}) has **changed** the `joinDM` option for `verified` members.", BROWN_COLOR)

        raise Message(f"Successfully **{parsed_args_1}d** your DM message.", type="success")

    @Fluxblox.subcommand()
    async def unverified(self, CommandArgs):
        """set the DM message of people who are UNVERIFIED on Fluxblox"""

        author = CommandArgs.author
        guild = CommandArgs.guild

        unverified_DM = await get_guild_value(guild, ["unverifiedDM", DEFAULTS.get("unverifiedDM")])

        response = CommandArgs.response

        if unverified_DM:
            response.delete(await response.send("When people join your server and are **UNVERIFIED** on Fluxblox, they will "
                                               f"receive this DM:"))
            response.delete(await response.send(f"```{unverified_DM}```"))


        parsed_args_1 = (await CommandArgs.prompt([{
            "prompt": "Would you like to **change** the DM people get when they join and are unverified, or "
                        "would you like to **disable** this feature?\n\nPlease specify: (change, disable)",
            "name": "option",
            "type": "choice",
            "choices": ("change", "disable")
        }]))["option"]

        if parsed_args_1 == "change":
            parsed_args_2 = (await CommandArgs.prompt([{
                "prompt": "What would you like the text of the Unverified Join DM to be? You may use "
                            f"these templates: ```{UNVERIFIED_TEMPLATES}```",
                "name": "text",
                "formatting": False
            }], last=True))["text"]

            await set_guild_value(guild, unverifiedDM=parsed_args_2)

        elif parsed_args_1 == "disable":
            await set_guild_value(guild, unverifiedDM=None)

        await post_event(guild, "configuration", f"{author.mention} ({author.id}) has **changed** the `joinDM` option for `unverified` members.", BROWN_COLOR)

        raise Message(f"Successfully **{parsed_args_1}d** your DM message.", type="success")
