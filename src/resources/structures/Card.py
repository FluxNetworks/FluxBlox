from ..structures import Fluxblox, InteractionPaginator # pylint: disable=import-error, no-name-in-module
from ..constants import Fluxblox_STAFF
from ..secrets import IMAGE_SERVER_URL, IMAGE_SERVER_AUTH
from io import BytesIO
import enum
import discord


fetch = Fluxblox.get_module("utils", attrs=["fetch"])
set_user_value, set_db_value, get_db_value, get_user_value = Fluxblox.get_module("cache", attrs=["set_user_value", "set_db_value", "get_db_value", "get_user_value"])
has_premium = Fluxblox.get_module("premium", attrs=["has_premium"])


class MoreInformationSelect(discord.ui.Select):
    def __init__(self, roblox_user):
        self.roblox_user = roblox_user

        options = [
            discord.SelectOption(label=o) for o in ("Roblox Username", "Roblox ID", "Display Name", "Description", "Profile URL")
        ]

        super().__init__(placeholder="Get the text of...", options=options)

    async def callback(self, interaction: discord.Interaction):
        chosen_option = interaction.data["values"][0]

        if chosen_option == "Roblox Username":
            value = self.roblox_user.name
        elif chosen_option == "Roblox ID":
            value = self.roblox_user.id
        elif chosen_option == "Display Name":
            value = self.roblox_user.display_name
        elif chosen_option == "Description":
           value = self.roblox_user.description[:2000] or "No description available."
        elif chosen_option == "Profile URL":
            value = self.roblox_user.profile_link

        await interaction.response.send_message(value, ephemeral=True)


class CardSide(enum.Enum):
    FRONT = 1
    BACK  = 2

class Card(Fluxblox.Module):
    def __init__(self, user, author, author_accounts, roblox_user, type, guild=None, extra_components=None, extra_data=None, from_interaction=True):
        self.response = None
        self.user = user
        self.author = author
        self.guild = guild
        self.type = type
        self.author_accounts = author_accounts
        self.extra_data = extra_data or {}
        self.view = discord.ui.View(timeout=1000.0)
        self.paginator = None
        self.user_backgrounds = {}
        self.user_tokens = 0
        self.merch_unlocked = False
        self.equipped_background = None
        self.message = None
        self.roblox_user = roblox_user
        self.extra_components = extra_components or []

        self.premium_user = False

        self.from_interaction = from_interaction
        self.interaction_args = {"hidden": True} if self.from_interaction else {}

        self.group_ranks = {}

        self.front_card_bytes = self.back_card_bytes = None
        self.front_card_file  = self.back_card_file  = None

        self.side = CardSide.FRONT

    async def __call__(self):
        if not self.roblox_user.complete:
            if self.type == "getinfo":
                await self.roblox_user.sync(includes=True)
            else:
                await self.roblox_user.sync(everything=True)

        self.add_profile_hyperlink_button()

        if self.type == "getinfo":
            self.add_specific_infomation_select()
            await self.roblox_user.parse_flags() # unsupported by old RobloxUsers
            await self.fetch_request_group_ranks()

            if self.group_ranks:
                self.add_flip_card_button()

        if self.roblox_user.id in self.author_accounts:
            self.add_change_background_button()

        # self.add_invite_button()

        if self.extra_components:
            for component in self.extra_components:
                self.view.add_item(item=component)

        await self.request_front_card()

        self.premium_user = "premium" in (await has_premium(user=self.user)).features

    async def fetch_request_group_ranks(self):
        if self.guild and not self.group_ranks:
            self.group_ranks = await self.roblox_user.get_group_ranks(self.guild)

    async def request_front_card(self):
        if not self.front_card_bytes:
            if self.type == "getinfo":
                profile_image_bytes, http_response = await fetch(f"{IMAGE_SERVER_URL}/getinfo/front", bytes=True, body={
                    "background": await Card.get_equipped_background(self.roblox_user.id) or "null",
                    "username": self.roblox_user.name,
                    "display_name": self.roblox_user.display_name,
                    "description": self.roblox_user.description,
                    "headshot": self.roblox_user.avatar,
                    # "overlay": self.roblox_user.overlay,
                    "id": self.roblox_user.id,
                    "age": self.roblox_user.short_age_string,
                    "banned": self.roblox_user.banned
                }, headers={"Authorization": IMAGE_SERVER_AUTH})
            elif self.type == "verify":
                profile_image_bytes, http_response = await fetch(f"{IMAGE_SERVER_URL}/verify/front", bytes=True, body={
                    "background": await Card.get_equipped_background(self.roblox_user.id) or "null",
                    "username": self.roblox_user.name,
                    "display_name": self.roblox_user.display_name,
                    "headshot": self.roblox_user.avatar,
                    "nickname": self.extra_data.get("nickname"),
                    "roles": {"added": self.extra_data.get("added"), "removed": self.extra_data.get("removed")},
                    "warnings": self.extra_data.get("warnings"),
                    "errors": self.extra_data.get("errors")
                }, headers={"Authorization": IMAGE_SERVER_AUTH})

            self.front_card_bytes = profile_image_bytes

        self.front_card_file = discord.File(BytesIO(self.front_card_bytes), filename="profile.png")

    async def request_back_card(self):
        if not self.back_card_bytes:
            if self.type == "getinfo":
                profile_image_bytes, http_response = await fetch(f"{IMAGE_SERVER_URL}/getinfo/back", bytes=True, body={
                    "background": await Card.get_equipped_background(self.roblox_user.id) or "null",
                    "username": self.roblox_user.name,
                    "display_name": self.roblox_user.display_name,
                    "group_ranks": self.group_ranks or {},
                    "banned": self.roblox_user.banned
                }, headers={"Authorization": IMAGE_SERVER_AUTH})

            self.back_card_bytes = profile_image_bytes

        self.back_card_file = discord.File(BytesIO(self.back_card_bytes), filename="profile.png")

    async def get_backgrounds(self):
        backgrounds, http_response = await fetch(f"{IMAGE_SERVER_URL}/backgrounds/", params={
            "type": self.type
        }, headers={"Authorization": IMAGE_SERVER_AUTH})

        if http_response.status == 200:
            return backgrounds

        return []

    async def buy_background(self, background_name):
        unlocks = await self.get_user_unlocks()

        if (not self.user_tokens or background_name in self.user_backgrounds) and not self.roblox_user.flags & FLUXBLOX_STAFF:
            return False

        unlocks["tokens"]["backgrounds"] -= 1
        unlocks["backgrounds"][background_name] = True

        self.paginator.unlocked = True
        self.paginator.custom_button.label = "Equip Background"
        self.paginator.custom_button.style = discord.ButtonStyle.success

        await self.paginator.message.edit(view=self.paginator)

        await set_user_value(self.user, unlocks=unlocks)

        return True

    def equip_background(self, background_name):
        async def click(interaction):
            if interaction:
                if self.from_interaction:
                    self.response.renew(interaction)

            self.paginator.custom_button.label = "Equipped"
            self.paginator.custom_button.disabled = True
            self.paginator.custom_button.style = discord.ButtonStyle.success

            await self.paginator.message.edit(view=self.paginator)

            self.equipped_background = background_name

            await set_db_value("roblox_profiles", self.roblox_user, background=background_name)

            await self.response.send("Successfully equipped your background! Go view it with `/getinfo`!", **self.interaction_args)

        return click

    async def custom_button_click(self, interaction):
        if self.from_interaction:
            self.response.renew(interaction)

        background_data = self.paginator.current_items[0][3]

        if self.paginator.unlocked or background_data.get("free"):
            await (self.equip_background(self.paginator.current_items[0][2])(None))
        elif (self.user_tokens > 0 and background_data.get("acquirable")) or (self.roblox_user.flags & FLUXBLOX_STAFF) or (background_data.get("merch") and self.merch_unlocked) or (self.user.id in background_data.get("unlocked", [])):
            # TODO: check to make sure background isn't already unlocked

            success = await self.buy_background(self.paginator.current_items[0][2])

            if success:
                view = discord.ui.View()

                equip_background_button = discord.ui.Button(label="Equip Background", style=discord.ButtonStyle.success)
                equip_background_button.callback = self.equip_background(self.paginator.current_items[0][2])

                view.add_item(item=equip_background_button)

                await self.response.send("Successfully unlocked background!", view=view, **self.interaction_args)
            else:
                await self.response.send("Something went wrong with the purchase.", **self.interaction_args)

        else:
            on_buy_message = background_data.get("on_buy_message")

            if on_buy_message:
                await self.response.send(on_buy_message, **self.interaction_args)
            else:
                await self.response.send("You can purchase this background from: <https://shop.blox.link/products/user-background>. Then, use the `/redeem` command with the code sent to your email.", **self.interaction_args)


    async def on_page_change(self):
        if not self.paginator.current_items:
            self.paginator.custom_button.disabled = True
            self.paginator.custom_button.label = "Purchase Background"
            self.paginator.custom_button.style = discord.ButtonStyle.secondary
        else:
            background_data = self.paginator.current_items[0][3]

            self.paginator.unlocked = self.premium_user or self.paginator.current_items[0][2] in self.user_backgrounds or self.user.id in background_data.get("unlocked", [])
            self.paginator.custom_button.disabled = False

            if self.equipped_background == self.paginator.current_items[0][2]:
                self.paginator.custom_button.label = "Equipped"
                self.paginator.custom_button.disabled = True
                self.paginator.custom_button.style = discord.ButtonStyle.success
            elif self.paginator.unlocked or background_data.get("free"):
                self.paginator.custom_button.label = "Equip Background"
                self.paginator.custom_button.style = discord.ButtonStyle.success
            elif (self.user_tokens > 0 and background_data.get("acquirable")) or (self.roblox_user.flags & FLUXBLOX_STAFF) or (background_data.get("merch") and self.merch_unlocked):
                self.paginator.custom_button.label = "Unlock Background"
                self.paginator.custom_button.style = discord.ButtonStyle.success
            else:
                self.paginator.custom_button.label = "Purchase Background"
                self.paginator.custom_button.style = discord.ButtonStyle.secondary

    async def get_user_unlocks(self):
        unlocks = await get_user_value(self.user, "unlocks") or {}

        unlocks["backgrounds"] = unlocks.get("backgrounds") or {}
        unlocks["tokens"] = unlocks.get("tokens") or {}
        unlocks["tokens"]["backgrounds"] = unlocks["tokens"].get("backgrounds", 0)

        self.user_tokens = unlocks["tokens"]["backgrounds"]
        self.user_backgrounds = unlocks["backgrounds"]
        self.merch_unlocked = unlocks.get("merch")

        return unlocks

    @staticmethod
    async def get_equipped_background(roblox_id):
        return await get_db_value("roblox_profiles", roblox_id, "background")

    async def get_paginator(self, **backgrounds):
        paginator = InteractionPaginator({
                        "All Backgrounds": backgrounds.get("all_backgrounds"),
                        "Limited Time Backgrounds": backgrounds.get("limited_time"),
                        "Free Backgrounds": backgrounds.get("free_backgrounds"),
                        "Unlocked Backgrounds": backgrounds.get("unlocked_backgrounds")
                    }, self.response, max_items=1, use_fields=False, use_embed_pictures=True, initialize_components=False, default_category="All Backgrounds", ephemeral=True, description="Find the perfect background for your profile!")

        paginator.initialize_buttons("back_button")

        paginator.custom_button = discord.ui.Button(label="Purchase Background", style=discord.ButtonStyle.success)
        paginator.custom_button.callback = self.custom_button_click
        paginator.add_item(paginator.custom_button)

        paginator.initialize_buttons("forward_button")

        paginator.on_page_change = self.on_page_change

        return paginator

    async def change_background_button_click(self, interaction):
        if interaction.user != self.author:
            await interaction.response.send_message(f"This button can only be clicked by {self.author.mention}.", ephemeral=True)
            return

        if self.from_interaction:
            self.response.renew(interaction)

        await self.get_user_unlocks()
        self.equipped_background = await Card.get_equipped_background(self.roblox_user.id)

        all_backgrounds = []
        limited_time_backgrounds = []
        free_backgrounds = []
        unlocked_backgrounds = []

        for background_id, background in (await self.get_backgrounds()).items():
            background_categories = background.get("categories") or []
            background_url = f"{IMAGE_SERVER_URL}/{background['paths'][self.type]['whole']}"
            background_name = background["name"]
            background_available = background["available"]
            background_unlocked = background.get("unlocked", [])

            if background_available:
                for background_category in background_categories:
                    if background_category == "Limited Time":
                        limited_time_backgrounds.append((background_name, background_url, background_id, background))
                    elif background_category == "Free Backgrounds":
                        free_backgrounds.append((background_name, background_url, background_id, background))

                if not background.get("exclude_from_all_backgrounds"):
                    all_backgrounds.append((background_name, background_url, background_id, background))

            if background_id in self.user_backgrounds or self.user.id in background_unlocked:
                unlocked_backgrounds.append((background_name, background_url, background_id, background))

        self.paginator = await self.get_paginator(all_backgrounds=all_backgrounds, limited_time=limited_time_backgrounds, free_backgrounds=free_backgrounds, unlocked_backgrounds=unlocked_backgrounds)

        await self.paginator()

    async def flip_card_button_click(self, interaction):
        if interaction.user != self.author:
            await interaction.response.send_message(f"This button can only be clicked by {self.author.mention}.", ephemeral=True)
            return

        if self.from_interaction:
            self.response.renew(interaction)
            await interaction.response.defer(thinking=False)

        if self.side == CardSide.FRONT:
            await self.request_back_card()
            await self.message.edit(attachments=[self.back_card_file])

            self.side = CardSide.BACK
        else:
            await self.request_front_card()
            await self.message.edit(attachments=[self.front_card_file])

            self.side = CardSide.FRONT

    def add_change_background_button(self):
        button = discord.ui.Button(style=discord.ButtonStyle.primary, label="Change Background", emoji="<:paint:927445603666001930>")
        button.callback = self.change_background_button_click

        self.view.add_item(item=button)
        self.view.timeout = 1000

    def add_flip_card_button(self):
        button = discord.ui.Button(style=discord.ButtonStyle.success, label="Flip Card", emoji="<:flip:927444361837428796>")
        button.callback = self.flip_card_button_click

        self.view.add_item(item=button)
        self.view.timeout = 1000

    def add_profile_hyperlink_button(self):
        self.view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Visit Profile", url=self.roblox_user.profile_link, emoji="<:profile:927447203029606410>"))

    def add_invite_button(self):
        self.view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Add Fluxblox to your Server", url="https://discord.com/oauth2/authorize?scope=bot%20applications.commands&client_id=426537812993638400&permissions=1007021144", emoji="<:invite:959934044659937320>"))

    def add_specific_infomation_select(self):
        self.view.add_item(item=MoreInformationSelect(self.roblox_user))
