class DonatorProfile:
    def __init__(self, *, user=None, guild=None, typex=None, expiry=None, term=None, tier=None, user_facing_tier=None, features=None, old_premium=False):
        features = features or set()

        self.user = user
        self.guild = guild
        self.type = typex
        self.expiry = expiry
        self.term = term
        self.tier = tier
        self.user_facing_tier = user_facing_tier
        self.features = features
        self.old_premium = old_premium

        # old stuff
        self.days = None

    def add_features(self, *args):
        map(self.features.add, args)
