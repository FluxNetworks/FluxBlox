from ..structures.Fluxblox import Fluxblox # pylint: disable=import-error, no-name-in-module
import traceback

"""
@Fluxblox.event
async def on_error(event, *args, **kwargs):
    Fluxblox.error(event=event)
"""

@Fluxblox.event
async def on_error(event, *args, **kwargs):
    error = traceback.format_exc()
    Fluxblox.error(error, title=f"Error source: {event}.py")