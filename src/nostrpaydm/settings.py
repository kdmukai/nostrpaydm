import json
from nostr.key import PrivateKey, PublicKey
from typing import List



class Settings:
    DEFAULT_CONFIG_FILENAME = "settings.json"

    # fields
    NOSTR_PRIVATE_KEY = "nostr_private_key"
    NOSTR_PUBLIC_KEY = "nostr_public_key"
    NOSTR_RELAYS = "relays"
    LAST_DM_PROCESSED = "last_dm_processed"
    BITCOIN_XPUB = "bitcoin_xpub"
    CHILD_INDEX = "child_index"


    # class instance fields
    config_filename: str


    def __init__(self, config_filename: str = DEFAULT_CONFIG_FILENAME):
        self.config_filename = config_filename
        try:
            with open(config_filename, 'r') as config_file:
                self._settings = json.load(config_file)
                print(json.dumps(self._settings, indent=4))
        except FileNotFoundError:
            self._settings = {}

        if Settings.NOSTR_RELAYS not in self._settings:
            self._settings[Settings.NOSTR_RELAYS] = []

        if Settings.CHILD_INDEX not in self._settings:
            self._settings[Settings.CHILD_INDEX] = 0


    @property
    def nostr_private_key(self) -> PrivateKey:
        return PrivateKey.from_nsec(self._settings.get(Settings.NOSTR_PRIVATE_KEY))
    

    @property
    def nostr_private_key_hex(self) -> str:
        private_key = self._settings.get(Settings.NOSTR_PRIVATE_KEY)
        return PrivateKey.from_nsec(private_key).hex() if private_key is not None else None


    @property
    def nostr_public_key(self) -> PublicKey:
        return PublicKey.from_npub(self._settings.get(Settings.NOSTR_PUBLIC_KEY))
    

    @property
    def nostr_public_key_hex(self) -> str:
        public_key = self._settings.get(Settings.NOSTR_PUBLIC_KEY)
        return PublicKey.from_npub(public_key).hex() if public_key is not None else None


    @property
    def relays(self) -> List[str]:
        return self._settings.get(Settings.NOSTR_RELAYS)
    

    @property
    def last_dm_processed(self) -> int:
        """ The Event.created_at timestamp of the most recent incoming DM processed """
        return self._settings.get(Settings.LAST_DM_PROCESSED)


    @property
    def bitcoin_xpub(self) -> str:
        return self._settings.get(Settings.BITCOIN_XPUB)


    @property
    def cur_child_index(self) -> int:
        return self._settings[Settings.CHILD_INDEX]


    def set_nostr_keys(self, nsec: str, npub: str):
        self._settings[Settings.NOSTR_PRIVATE_KEY] = nsec
        self._settings[Settings.NOSTR_PUBLIC_KEY] = npub
        self.save()
    

    def add_relay(self, relay: str):
        self._settings[Settings.NOSTR_RELAYS].append(relay)
        self.save()
    

    def clear_relays(self):
        self._settings[Settings.NOSTR_RELAYS] = []
        self.save()
    

    def set_last_dm_processed(self, dm_created_at: int):
        self._settings[Settings.LAST_DM_PROCESSED] = dm_created_at
        self.save()


    def set_bitcoin_xpub(self, xpub: str):
        self._settings[Settings.BITCOIN_XPUB] = xpub
        self.save()


    def increment_child_index(self):
        self._settings[Settings.CHILD_INDEX] += 1
        self.save()


    def save(self):
        with open(self.config_filename, 'w') as config_file:
            config_file.write(json.dumps(self._settings, indent=4))
