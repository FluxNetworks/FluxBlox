from ...structures.Fluxblox import Fluxblox # pylint: disable=no-name-in-module, import-error



@Fluxblox.module
class Groups(Fluxblox.Module):
    def __init__(self):
        pass

    async def get_group(self, group_id):
        raise NotImplementedError()


class Group:
    def __init__(self, group_meta, group_role):
        self.name = group_meta["name"]
        self.id = str(group_meta["id"])

        self.rank_name = group_role["name"]
        self.rank_value = group_role["rank"]


    async def sync(self):
        raise NotImplementedError()

    def __str__(self):
        return f"{self.name} ({self.id})"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return self.id == getattr(other, "id", -1)
