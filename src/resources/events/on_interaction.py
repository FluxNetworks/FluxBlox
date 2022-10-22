from ..structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
from ..exceptions import CancelCommand # pylint: disable=import-error, no-name-in-module
from discord import User, Message, PartialMessageable
from ..constants import RELEASE # pylint: disable=import-error, no-name-in-module


execute_interaction_command, send_autocomplete_options = Fluxblox.get_module("commands", attrs=["execute_interaction_command", "send_autocomplete_options"])


@Fluxblox.event
async def on_interaction(interaction):
    data = interaction.data
    command_name = interaction.data.get("name")
    command_args = {}

    channel = interaction.channel
    guild   = interaction.guild

    if isinstance(channel, PartialMessageable) and guild:
        channel = guild.get_channel(channel.id)

        if not channel:
            return


    if not data.get("type"):
        return

    if data["type"] in (2, 3): # context menu command
        resolved = None

        if data.get("resolved"):
            if data["resolved"].get("users"):
                resolved = User(state=interaction._state, data=list(data["resolved"]["users"].values())[0])
            else:
                resolved = Message(state=interaction._state, channel=channel, data=list(data["resolved"]["messages"].values())[0])

        try:
            await execute_interaction_command("extensions", command_name, interaction=interaction, resolved=resolved)
        except CancelCommand:
            pass

    elif data["type"] == 1: # slash command
        if not command_name:
            return

        subcommand = None
        focused_option = None

        if data.get("options"):
            if RELEASE == "LOCAL":
                print(data["options"])

            for arg in data["options"]:
                if arg.get("options"):
                    subcommand = arg["name"]

                    for arg2 in arg["options"]:
                        if arg2.get("focused"):
                            focused_option = arg2

                        command_args[arg2["name"]] = arg2["value"]
                else:
                    if arg.get("value") is not None:
                        if arg.get("focused"):
                            focused_option = arg

                        command_args[arg["name"]] = arg["value"]
                    else:
                        subcommand = arg["name"]

        if focused_option:
            await send_autocomplete_options(interaction, command_name, subcommand, command_args, focused_option)
            return

        # execute slash command
        try:
            await execute_interaction_command("commands", command_name, interaction=interaction, subcommand=subcommand,
                                              arguments=command_args)
        except CancelCommand:
            pass
