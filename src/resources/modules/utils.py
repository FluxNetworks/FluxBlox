from os import listdir
from re import compile
from ..structures import Fluxblox # pylint: disable=import-error, no-name-in-module, no-name-in-module
from ..exceptions import RobloxAPIError, RobloxDown, RobloxNotFound # pylint: disable=import-error, no-name-in-module, no-name-in-module
from ..constants import RELEASE, HTTP_RETRY_LIMIT # pylint: disable=import-error, no-name-in-module, no-name-in-module
from ..secrets import TOKEN, PROXY_URL, PROXY_AUTH # pylint: disable=import-error, no-name-in-module, no-name-in-module
from ..exceptions import Error
from discord.errors import NotFound, Forbidden
import discord
from requests.utils import requote_uri
import asyncio
import aiohttp
import json as json_


get_guild_value, set_guild_value = Fluxblox.get_module("cache", attrs=["get_guild_value", "set_guild_value"])

@Fluxblox.module
class Utils(Fluxblox.Module):
    def __init__(self):
        self.option_regex = compile("(.+):(.+)")
        self.timeout = None
        self.session = None
        self.loop = None

    @staticmethod
    def get_files(directory):
        return [name for name in listdir(directory) if name[:1] != "." and name[:2] != "__" and name != "_DS_Store"]

    @staticmethod
    def coro_async(corofn, *args):
        # https://stackoverflow.com/questions/46074841/why-coroutines-cannot-be-used-with-run-in-executor
        loop = asyncio.new_event_loop()

        try:
            coro = corofn(*args)
            asyncio.set_event_loop(loop)

            return loop.run_until_complete(coro)

        finally:
            loop.close()

    @staticmethod
    async def suppress_timeout_errors(awaitable):
        try:
            return await awaitable
        except asyncio.TimeoutError:
            pass

    async def post_event(self, guild, event_name, text, color=None):
        options = await get_guild_value(guild, "logChannels", "highTrafficServer") or {}
        log_channels = options.get("logChannels") or {}
        log_channel  = log_channels.get(event_name) or log_channels.get("all")
        high_traffic_server = options.get("highTrafficServer")

        webhook = None

        if high_traffic_server and event_name == "verification":
            return

        if log_channel:
            if isinstance(log_channel, str): # old data
                text_channel = guild.get_channel(int(log_channel))

                if text_channel:
                    permissions = text_channel.permissions_for(guild.me)

                    if not permissions.manage_webhooks:
                        raise Error("Events are enabled but I couldn't create the webhook! Please make sure I have the `Manage Webhooks` permission.")

                    webhook = discord.utils.find(lambda w: w.name == "Fluxblox Webhooks", await text_channel.webhooks())

                    if not webhook:
                        webhook = await text_channel.create_webhook(name="Fluxblox Webhooks", reason="Created webhook for event")

                    log_channels[event_name] = {
                        "channel": log_channel,
                        "webhook": {
                            "id": str(webhook.id),
                            "token": webhook.token
                        }
                    }

                    webhook = discord.Webhook.partial(id=int(webhook.id), token=webhook.token, bot_token=TOKEN, session=self.session) # so we can authenticate the webhook with a bot token

                    await set_guild_value(guild, logChannels=log_channels)

            else:
                webhook = discord.Webhook.partial(id=log_channel["webhook"]["id"], token=log_channel["webhook"]["token"], bot_token=TOKEN, session=self.session)

            if not webhook:
                return

            if not webhook.token:
                return

            embed = discord.Embed(title=f"{event_name.title()} Event", description=text)
            embed.colour = color

            try:
                await webhook.send(embed=embed)
            except (Forbidden, NotFound):
                pass

    async def fetch(self, url, method="GET", params=None, headers=None, body=None, text=False, json=True, bytes=False, raise_on_failure=True, retry=HTTP_RETRY_LIMIT, timeout=20, proxy=True):
        params  = params or {}
        headers = headers or {}
        proxied = False

        if not self.loop:
            self.loop = asyncio.get_event_loop()

        if not self.timeout:
            self.timeout = aiohttp.ClientTimeout(total=20)

        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout, loop=self.loop)

        if text or bytes:
            json = False

        if retry and proxy and PROXY_AUTH and "roblox.com" in url:
            old_url = url
            url = PROXY_URL
            proxied = True
            real_method = method
            method = "POST"
            body = {
                "url": old_url,
                "method": real_method,
                "data": body
            }
            headers["Authorization"] = PROXY_AUTH

            if RELEASE == "LOCAL":
                print(f"{old_url} -> {url}")
        else:
            if RELEASE == "LOCAL":
                print(f"Making request to {url} with method {method}")

            old_url = url

        url = requote_uri(url)

        for k, v in params.items():
            if isinstance(v, bool):
                params[k] = "true" if v else "false"

        try:
            async with self.session.request(method, url, json=body, params=params, headers=headers, timeout=self.timeout) as response:
                if proxied:
                    try:
                        response_json = await response.json()
                    except aiohttp.client_exceptions.ContentTypeError:
                        print(old_url, await response.text())
                        raise RobloxAPIError()

                    response_body = response_json

                    if not isinstance(response_json, dict):
                        try:
                            response_body_json = json_.loads(response_body)
                        except json_.decoder.JSONDecodeError:
                            pass
                        else:
                            response_body = response_body_json
                else:
                    response_body = None

                if response.status == 429 and retry and "roblox.com" in old_url:
                    return await self.fetch(url=url, method=method, params=params, headers=headers, body=body, text=text, json=json, bytes=bytes, raise_on_failure=raise_on_failure, retry=retry-1, timeout=timeout, proxy=True)

                if raise_on_failure:
                    if response.status == 503:
                        raise RobloxDown
                    elif response.status == 404:
                        raise RobloxNotFound
                    elif response.status >= 400:
                        if proxied:
                            print(old_url, response_body, flush=True)
                        else:
                            print(old_url, await response.text(), flush=True)
                        raise RobloxAPIError

                    if json:
                        if not proxied:
                            try:
                                response_body = await response.json()
                            except aiohttp.client_exceptions.ContentTypeError:
                                raise RobloxAPIError

                        if isinstance(response_body, dict):
                            return response_body, response
                        else:
                            return {}, response

                if text:
                    if proxied:
                        return str(response_body), response

                    text = await response.text()

                    return text, response

                elif json:
                    if proxied:
                        if not isinstance(response_body, dict):
                            print("Roblox API Error: ", old_url, type(response_body), response_body, flush=True)

                            if raise_on_failure:
                                raise RobloxAPIError

                        return response_body, response

                    try:
                        json = await response.json()
                    except aiohttp.client_exceptions.ContentTypeError:
                        print(old_url, await response.text(), flush=True)

                        raise RobloxAPIError

                    return json, response

                elif bytes:
                    return await response.read(), response

                return response

        except asyncio.TimeoutError:
            print(f"URL {old_url} timed out", flush=True)
            raise RobloxDown

    # async def fetch(self, url, method="GET", params=None, headers=None, json=None, body=None, text=True, bytes=False, raise_on_failure=True, retry=HTTP_RETRY_LIMIT, timeout=20):
    #     params  = params or {}
    #     headers = headers or {}

    #     url = requote_uri(url)

    #     if RELEASE == "LOCAL":
    #         Fluxblox.log(f"Making HTTP request: {url}")

    #     for k, v in params.items():
    #         if isinstance(v, bool):
    #             params[k] = "true" if v else "false"

    #     if bytes or json:
    #         text = False

    #     # if "roblox.com" in url:
    #     proxy = "aaa"
    #     # else:
    #     #     proxy = None

    #     try:
    #         async with a_timeout(timeout): # I noticed sometimes the aiohttp timeout parameter doesn't work. This is added as a backup.
    #             async with self.session.request(method, url, json=body, params=params, headers=headers, timeout=timeout, proxy=proxy) as response:
    #                 if response.status == 503:
    #                     raise RobloxDown

    #                 if raise_on_failure:
    #                     if response.status >= 500:
    #                         if retry != 0:
    #                             retry -= 1
    #                             await asyncio.sleep(1.0)

    #                             return await self.fetch(url, raise_on_failure=raise_on_failure, bytes=bytes, json=json, text=text, params=params, headers=headers, retry=retry, timeout=timeout)

    #                         raise RobloxAPIError

    #                     elif response.status == 400:
    #                         raise RobloxAPIError
    #                     elif response.status == 404:
    #                         raise RobloxNotFound

    #                 if bytes:
    #                     return await response.read(), response
    #                 elif text:
    #                     return await response.text(), response
    #                 elif json:
    #                     return await response.json(), response

    #     except ServerDisconnectedError:
    #         if retry != 0:
    #             return await self.fetch(url, retry=retry-1, raise_on_failure=raise_on_failure, bytes=bytes, json=json, text=text, params=params, headers=headers, timeout=timeout)
    #         else:
    #             raise ServerDisconnectedError

    #     except ClientOSError:
    #         # TODO: raise HttpError with non-roblox URLs
    #         raise RobloxAPIError

    #     except asyncio.TimeoutError:
    #         raise RobloxDown
