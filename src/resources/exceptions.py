class FluxbloxException(Exception):
    def __init__(self, message=None, type="error", dm=False, hidden=False):
        self.type = type
        self.dm = dm # only implemented in a few places
        self.hidden = hidden
        self.message = message


class CancelCommand(FluxbloxException):
    pass

class Messages(CancelCommand):
    def __init__(self, *args, type="send", **kwargs):
        super().__init__(*args, type=type, **kwargs)

class Message(Messages):
    def __init__(self, *args, type="send", **kwargs):
        super().__init__(*args, type=type, **kwargs)

class Error(Messages):
    def __init__(self, *args, type="send", **kwargs):
        super().__init__(*args, type=type, **kwargs)

class CancelledPrompt(CancelCommand):
    def __init__(self, *args, type="send", **kwargs):
        super().__init__(*args, type=type, **kwargs)


class PermissionError(FluxbloxException):
    pass

class BadUsage(FluxbloxException):
    pass

class RobloxAPIError(FluxbloxException):
    pass

class RobloxNotFound(FluxbloxException):
    pass

class RobloxDown(FluxbloxException):
    pass

class UserNotVerified(FluxbloxException):
    pass

class FluxbloxBypass(FluxbloxException):
    pass

class Blacklisted(FluxbloxException):
    def __init__(self, *args, guild_restriction=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.guild_restriction = guild_restriction
