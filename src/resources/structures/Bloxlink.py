from importlib import import_module
from os import environ as env
from discord import AutoShardedClient, AllowedMentions, Intents, Game
from config import WEBHOOKS # pylint: disable=E0611
from ..constants import SHARD_RANGE, CLUSTER_ID, SHARD_COUNT, RELEASE, SELF_HOST, PLAYING_STATUS # pylint: disable=import-error, no-name-in-module
from ..secrets import (REDIS_CONNECTION_STRING, MONGO_CONNECTION_STRING, MONGO_CA_FILE, DISCORD_PROXY) # pylint: disable=import-error, no-name-in-module)
from . import Permissions # pylint: disable=import-error, no-name-in-module
from os.path import exists
import functools
import traceback
import datetime
import logging
import aiohttp
import aredis
#import sentry_sdk
import asyncio
import motor.motor_asyncio



LOG_LEVEL = env.get("LOG_LEVEL", "INFO").upper()
LABEL = env.get("LABEL", "Fluxblox")
SHARD_SLEEP_TIME = int(env.get("SHARD_SLEEP_TIME", "5"))

logger = logging.getLogger()


class FluxbloxStructure(AutoShardedClient):
    db_host_validated = False
    conn = None
    loaded_modules = {}

    def __init__(self, *args, **kwargs): # pylint: disable=W0235
        super().__init__(*args, **kwargs)
        self.loop = asyncio.get_event_loop()
        #loop.run_until_complete(self.get_session())
        self.loop.set_exception_handler(self._handle_async_error)


    if not SELF_HOST:
        async def before_identify_hook(self, shard_id, *, initial=False):
            await asyncio.sleep(SHARD_SLEEP_TIME)

    @staticmethod
    def get_database():
        if MONGO_CA_FILE:
            ca_file = exists("cert.crt")

            if not ca_file:
                with open("src/cert.crt", "w") as f:
                    f.write(MONGO_CA_FILE)

        db = motor.motor_asyncio.AsyncIOMotorClient(MONGO_CONNECTION_STRING, tlsCAFile="src/cert.crt" if MONGO_CA_FILE else None)["fluxblox"]
        db.get_io_loop = asyncio.get_running_loop

        return db

    @staticmethod
    def log(*text, level=LOG_LEVEL):
        print(f"{LABEL} | {LOG_LEVEL} | {'| '.join(text)}", flush=True)


    """
    def error(self, e=None, **kwargs):
        if not e:
            e = traceback.format_exc()

        logger.exception(e)

        with sentry_sdk.push_scope() as scope:
            for tag_name, tag_value in kwargs.items():
                if tag_name == "user":
                    scope.user = {"id": tag_value[0], "username": tag_value[1]}
                else:
                    scope.set_tag(tag_name, tag_value)

            scope.level = "error"

            return sentry_sdk.capture_exception()
    """
    def error(self, text, title=None):
        loop = asyncio.get_event_loop()
        logger.exception(text)

        loop.create_task(self._error(str(text), title=title))

    async def _error (self, text, title=None):
        if (not text) or text == "Unclosed connection":
            return

        webhook_data = {
            "username": "Cluster Instance",

            "embeds": [{
                "timestamp": datetime.datetime.now().isoformat(),
                "description": f"**Cluster:** {CLUSTER_ID}\n**Shards:** {str(SHARD_RANGE)}",
                "fields": [
                    {"name": "Traceback", "value": text[0:2000]}
                ],
                "color": 13319470,
            }]
        }

        if title:
            webhook_data["embeds"][0]["title"] = title

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                try:
                    await session.post(WEBHOOKS["ERRORS"], json=webhook_data)
                except Exception as e:
                    logger.exception(e)
                    pass

        except asyncio.TimeoutError:
            pass

    def _handle_async_error(self, loop, context):
        exception   = context.get("exception")
        future_info = context.get("future")
        title = None

        if exception:
            title = exception.__class__.__name__
            msg = "".join(traceback.format_exception(etype=type(exception), value=exception, tb=exception.__traceback__))
        else:
            msg = future_info and str(future_info) or str(context["message"])

        self.error(msg, title=title)

    @staticmethod
    def module(module):
        loop = asyncio.get_event_loop()
        new_module = module()

        module_name = module.__name__.lower()
        module_dir = module.__module__.lower()

        if hasattr(new_module, "__setup__"):
            asyncio.run_coroutine_threadsafe(new_module.__setup__(), loop)

        Fluxblox.log(f"Loaded {module_name}")

        if hasattr(new_module, "__loaded__"):
            asyncio.run_coroutine_threadsafe(new_module.__loaded__(), loop)

        if FluxbloxStructure.loaded_modules.get(module_dir):
            FluxbloxStructure.loaded_modules[module_dir][module_name] = new_module
        else:
            FluxbloxStructure.loaded_modules[module_dir] = {module_name: new_module}

        return new_module

    @staticmethod
    def loader(module):
        def load(*args, **kwargs):
            return module(*args, **kwargs)

        stuff = {}

        for attr in dir(module):
            stuff[attr] = getattr(module, attr)

        #FluxbloxStructure.loaded_modules[module.__name__.lower()] = [load, stuff]

        #return load

    @staticmethod
    def get_module(dir_name, *, name_override=None, name_override_pattern="", path="resources.modules", attrs=None):
        save_as  = f"{name_override_pattern.lower()}{(dir_name).lower()}"
        modules = FluxbloxStructure.loaded_modules.get(save_as)
        name_obj = (name_override or dir_name).lower()

        class_obj = None
        module = None

        if not modules:
            import_name = f"{path}.{dir_name}".replace("src/", "").replace("/",".").replace(".py","")

            try:
                module = import_module(import_name)
            except (ModuleNotFoundError, ImportError) as e:
                Fluxblox.log(f"ERROR | {e}")
                traceback_text = traceback.format_exc()
                traceback_text = len(traceback_text) < 500 and traceback_text or f"...{traceback_text[len(traceback_text)-500:]}"
                Fluxblox.error(traceback_text, title=f"{dir_name}.py")

            except Exception as e:
                Fluxblox.log(f"ERROR | Module {dir_name} failed to load: {e}")
                traceback_text = traceback.format_exc()
                traceback_text = len(traceback_text) < 500 and traceback_text or f"...{traceback_text[len(traceback_text)-500:]}"
                Fluxblox.error(traceback_text, title=f"{dir_name}.py")
            else:
                for attr_name in dir(module):
                    if attr_name.lower() == name_obj:
                        class_obj = getattr(module, attr_name)
                        break

        if not attrs:
            return module or class_obj

        if class_obj is None and module:
            for attr_name in dir(module):
                if attr_name.lower() == name_obj:
                    class_obj = getattr(module, attr_name)

                    break


        if class_obj is not None:
            if attrs:
                attrs_list = list()

                if not isinstance(attrs, list):
                    attrs = [attrs]

                for attr in attrs:
                    if hasattr(class_obj, attr):
                        attrs_list.append(getattr(class_obj, attr))

                if len(attrs_list) == 1:
                    return attrs_list[0]
                else:
                    if not attrs_list:
                        return None

                    return (*attrs_list,)
            else:
                return class_obj

        raise RuntimeError(f"Unable to find module {name_obj} from {dir_name}")

    @staticmethod
    def command(*args, **kwargs):
        return Fluxblox.get_module("commands", attrs="new_command", name_override_pattern="Command_")(*args, **kwargs)

    @staticmethod
    def extension(*args, **kwargs):
        return Fluxblox.get_module("commands", attrs="new_extension", name_override_pattern="Extension_")(*args, **kwargs)

    @staticmethod
    def subcommand(**kwargs):
        def decorator(f):
            f.__issubcommand__ = True
            f.__subcommandattrs__ = kwargs

            @functools.wraps(f)
            def wrapper(self, *args):
                return f(self, *args)

            return wrapper

        return decorator

    @staticmethod
    def flags(fn):
        fn.__flags__ = True
        return fn

    Permissions = Permissions.Permissions # pylint: disable=no-member

    def __repr__(self):
        return "< Fluxblox Client >"


intents = Intents.none()

intents.members = True # pylint: disable=assigning-non-slot
intents.guilds = True # pylint: disable=assigning-non-slot
intents.guild_reactions = True # pylint: disable=assigning-non-slot
intents.dm_messages = True # pylint: disable=assigning-non-slot
intents.bans = True # pylint: disable=assigning-non-slot

if RELEASE == "PRO":
    intents.guild_typing = True # pylint: disable=assigning-non-slot


Fluxblox = FluxbloxStructure(
    chunk_guilds_at_startup=False,
    shard_count=SHARD_COUNT,
    shard_ids=SHARD_RANGE,
    allowed_mentions=AllowedMentions(everyone=False, users=True, roles=False),
    intents=intents,
    activity=Game(PLAYING_STATUS),
    proxy=DISCORD_PROXY if DISCORD_PROXY else None,
)


def load_redis():
    redis = redis_cache = None
    loop = asyncio.get_event_loop()

    try:
        redis = aredis.StrictRedis.from_url(
            REDIS_CONNECTION_STRING,
            retry_on_timeout=True,
            connect_timeout=3,
            socket_keepalive=True
        )
    except aredis.exceptions.ConnectionError:
        raise SystemError("Failed to connect to Redis.")
    else:
        redis_cache = redis.cache("cache")

    loop.create_task(redis_loop(redis))

    return redis, redis_cache

async def redis_loop(redis):
    while True:
        try:
            await redis.ping()
        except redis.exceptions.ConnectionError as e:
            raise SystemError("Failed to connect to Redis.") from e

        await asyncio.sleep(1)

redis, redis_cache = load_redis()

class Module:
    client = Fluxblox
    db = Fluxblox.get_database()
    loop = Fluxblox.loop
    redis = redis
    cache = redis_cache
    conn = Fluxblox.conn
    session = aiohttp.ClientSession()

Fluxblox.Module = Module
