from ..structures import Fluxblox # pylint: disable=import-error, no-name-in-module, no-name-in-module
from ..constants import CACHE_CLEAR # pylint: disable=import-error, no-name-in-module, no-name-in-module
from benedict import benedict


@Fluxblox.module
class Cache(Fluxblox.Module):
    def __init__(self):
        self._cache = benedict(keypath_separator=":")

    async def get(self, k, primitives=False, redis_hash=False, redis_hash_exists=False):
        if primitives and self.cache and k:
            if redis_hash:
                if redis_hash_exists:
                    return bool(await self.redis.hlen(k))
                else:
                    return await self.redis.hgetall(k)
            else:
                return await self.cache.get(k)

        return self._cache.get(k)


    async def set(self, k, v, expire=CACHE_CLEAR*60, check_primitives=True):
        if check_primitives and self.cache and isinstance(v, (str, int, bool, list)):
            await self.cache.set(k, v, expire_time=expire)
        else:
            self._cache[k] = v


    async def pop(self, k, primitives=False):
        if self.cache and primitives:
            if k:
                await self.cache.delete(k)
            else:
                await self.cache.delete_pattern(f"{k}*")
        else:
            self._cache.pop(k, None)


    async def clear(self, *exceptions):
        if exceptions:
            cache = benedict(keypath_separator=":")

            for exception in exceptions:
                cache_find = self._cache.get(exception)

                if cache_find:
                    cache[exception] = cache_find

            self._cache = cache
        else:
            self._cache = benedict(keypath_separator=":")


    async def get_db_value(self, typex, obj, *items):
        item_values = {}
        left_overs = {}

        idx = getattr(obj, "id", obj)

        if not items:
            mongo_data = await self.db[typex].find_one({"_id": str(idx)}) or {}

            return mongo_data


        for item_name in items:
            item_default = None

            if isinstance(item_name, list):
                item_default = item_name[1]
                item_name = item_name[0]

            data = await self.get(f"{typex}_data:{idx}:{item_name}", primitives=False)

            if data is not None:
                item_values[item_name] = data
            else:
                if item_default is not None:
                    item_values[item_name] = item_default

                left_overs[item_name] = 1

        if left_overs:
            left_overs["_id"] = 0
            mongo_data = await self.db[typex].find_one({"_id": str(idx)}, left_overs) or {}

            for k, v in mongo_data.items():
                await self.set(f"{typex}_data:{idx}:{k}", v, check_primitives=False)
                item_values[k] = v

        if len(items) == 1:
            return item_values.get(item_name)
        else:
            return item_values

    async def set_db_value(self, typex, obj, parent_value=None, skip_db=False, **items):
        insertion = {}
        unset     = {}

        idx = getattr(obj, "id", obj)

        if parent_value:
            await self.set(f"{typex}_data:{idx}", parent_value, check_primitives=False)

        for k,v in items.items():
            if k not in ("_id", "updatedAt"):
                if v is None:
                    unset[k] = ""
                else:
                    insertion[k] = v

            await self.set(f"{typex}_data:{idx}:{k}", v, check_primitives=False)

        if not skip_db:
            mongo_data = {
                "$currentDate": {
                    "updatedAt": True
                }
            }

            if insertion:
                mongo_data["$set"] = insertion
            if unset:
                mongo_data["$unset"] = unset

            await self.db[typex].update_one({"_id": str(idx)}, mongo_data, upsert=True)

    # convenience wrappers
    async def get_guild_value(self, guild, *items):
        return await self.get_db_value("guilds", guild, *items)

    async def get_user_value(self, user, *items):
        return await self.get_db_value("users", user, *items)

    async def set_guild_value(self, guild, guild_data=None, skip_db=False, **items):
        return await self.set_db_value("guilds", guild, parent_value=guild_data, skip_db=skip_db, **items)

    async def set_user_value(self, user, user_data=None, skip_db=False, **items):
        return await self.set_db_value("users", user, parent_value=user_data, skip_db=skip_db, **items)

    async def clear_guild_data(self, guild):
        await self.pop(f"guild_data:{guild.id}", primitives=False)

    async def clear_user_data(self, user):
        await self.pop(f"user_data:{user.id}", primitives=False)
