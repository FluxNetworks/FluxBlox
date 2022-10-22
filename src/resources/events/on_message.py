from ..structures import Fluxblox, Arguments # pylint: disable=import-error, no-name-in-module
from ..exceptions import CancelCommand # pylint: disable=import-error, no-name-in-module


parse_message = Fluxblox.get_module("commands", attrs="parse_message")


@Fluxblox.module
class MessageEvent:
	async def __setup__(self):
		@Fluxblox.event
		async def on_message(message):
			author = message.author

			if (author.bot or not message.channel or Arguments.in_prompt(author)) or (message.guild and message.guild.unavailable):
				return

			try:
				await parse_message(message)
			except CancelCommand:
				pass
