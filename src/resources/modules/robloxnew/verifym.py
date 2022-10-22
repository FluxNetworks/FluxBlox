from ...structures import Fluxblox, Response # pylint: disable=no-name-in-module, import-error
from ...exceptions import FluxbloxBypass, Blacklisted, PermissionError, UserNotVerified, RobloxDown, RobloxAPIError, CancelCommand # pylint: disable=import-error, no-name-in-module
from resources.constants import VERIFY_URL, VERIFY_URL_GUILD, DEFAULTS # pylint: disable=import-error, no-name-in-module
import discord

guild_obligations, format_update_embed, send_account_confirmation, get_user = Fluxblox.get_module("roblox", attrs=["guild_obligations", "format_update_embed", "send_account_confirmation", "get_user"]) # LEGACY METHODS
has_premium = Fluxblox.get_module("premium", attrs=["has_premium"])


@Fluxblox.module
class VerifyM(Fluxblox.Module):
    def __init__(self):
        self.client.add_view(self.VerificationView())

    class VerificationView(discord.ui.View):
        """adds a verification button that when pressed, verifies the user"""

        def __init__(self, verify_button_text=None, intro_message=None):
            super().__init__(timeout=None)

            if intro_message != DEFAULTS.get("verifyChannelTextModal"):
                self.add_item(item=discord.ui.Button(label="The text above was set by the Server Admins. ONLY verify from https://blox.link.",
                                                     disabled=True,
                                                     custom_id="warning:modified_content_button",
                                                     row=0))

            verify_button = discord.ui.Button(label=verify_button_text,
                                              emoji="<:chain:970894927196209223>",
                                              style=discord.ButtonStyle.green,
                                              custom_id="verify_view:verify_button",
                                              row=1)
            verify_button.callback = self.verify_button_click
            self.add_item(item=verify_button)

            self.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Need help?", emoji="❔",
                          url="https://www.youtube.com/playlist?list=PLz7SOP-guESE1V6ywCCLc1IQWiLURSvBE", row=1))


        async def verify_button_click(self, interaction: discord.Interaction):
            guild  = interaction.guild
            user   = interaction.user

            old_nickname = user.display_name

            response = Response.from_interaction(interaction)
            await response.slash_defer()

            try:
                roblox_user = (await get_user(user=user))[0]

                await send_account_confirmation(user, roblox_user, guild, response, ephemeral=True)

                added, removed, nickname, errors, warnings, roblox_user, bind_explanations = await guild_obligations(
                    response.args.author,
                    join                 = True,
                    roblox_user          = roblox_user,
                    guild                = guild,
                    roles                = True,
                    nickname             = True,
                    cache                = False,
                    response             = response,
                    dm                   = False,
                    exceptions           = ("FluxbloxBypass", "Blacklisted", "UserNotVerified", "PermissionError", "RobloxDown", "RobloxAPIError")
                )

            except FluxbloxBypass:
                await response.send("Since you have the `Fluxblox Bypass` role, I was unable to update your roles/nickname.", type="info")

            except Blacklisted as b:
                await response.send(b.message, hidden=True)

                return

            except UserNotVerified:
                verify_link = await VerifyM.get_verify_link(guild)

                await response.send(f"You are not verified with Fluxblox! You can verify by going to [https://blox.link/verify]({verify_link}).", hidden=True)


            except PermissionError as e:
                await response.send(e.message, hidden=True)

            except CancelCommand:
                return

            except RobloxDown:
                await response.send("Roblox is currently down. Please try again later.", hidden=True)

            except RobloxAPIError:
                await response.send("I encountered an unknown Roblox API error. Please try again later.", hidden=True)

            else:
                welcome_message, card, embed, view = await format_update_embed(
                    roblox_user,
                    user,
                    guild=guild,
                    added=added, removed=removed, errors=errors, warnings=warnings, nickname=nickname if old_nickname != nickname else None,
                    bind_explanations=bind_explanations
                )

                message = await response.send(welcome_message, files=[card.front_card_file] if card else None, view=card.view if card else view, embed=embed, hidden=True)

                if card:
                    card.response = response
                    card.message = message
                    card.view.message = message

                    #await post_event(guild, "verification", f"{user.mention} ({user.id}) has **verified** as `{roblox_user.username}`.", GREEN_COLOR)


    @staticmethod
    async def get_verify_link(guild):
        if guild:
            premium = await has_premium(guild=guild)

            if "premium" in premium.features and not premium.old_premium:
                return VERIFY_URL_GUILD.format(guild=guild.id)

        return VERIFY_URL


    async def update_user(self, user, guild):
        pass
