from ..structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module


@Fluxblox.event
async def on_ready():
    Fluxblox.log(f"Logged in as {Fluxblox.user.name}")
