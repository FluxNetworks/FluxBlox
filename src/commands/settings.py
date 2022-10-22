from resources.structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module, no-name-in-module


@Fluxblox.command
class SettingsCommand(Fluxblox.Module):
    """change, view, or reset your Fluxblox settings"""

    def __init__(self):
        self.permissions = Fluxblox.Permissions().build("FLUXBLOX_MANAGER")
        self.category = "Administration"
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response

        await CommandArgs.response.send("You can modify your settings from our dashboard: https://blox.link/dashboard")
