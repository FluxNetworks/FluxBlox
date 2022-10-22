import discord

class TimeoutView(discord.ui.View):
    def __init__(self, *args, **kwargs):
        self.message = None

        super().__init__(*args, **kwargs)

    async def on_timeout(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                if isinstance(child, discord.Button) and child.url:
                    continue

                child.disabled = True

        if self.message:
            await self.message.edit(view=self)
