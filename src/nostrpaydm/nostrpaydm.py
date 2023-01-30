import json
import ssl
import time
from typing import List, Tuple
from embit import bip32
from embit import script
from nostr.filter import Filter, Filters
from nostr.event import EventKind, Event, EncryptedDirectMessage
from nostr.relay_manager import RelayManager
from nostr.subscription import Subscription
from nostr.key import PrivateKey, PublicKey

from .settings import Settings



class NostrPayDM:
    def __init__(self, settings: Settings = None):
        if settings is None:
            # Load from defaults
            self.settings = Settings()
        else:
            self.settings = settings
        
        if not self.settings.nostr_private_key:
            # Generate a new  PK
            pk = PrivateKey()
            self.settings.set_nostr_keys(nsec=pk.bech32(), npub=pk.public_key.bech32())

        self.relay_manager = RelayManager({"cert_reqs": ssl.CERT_NONE})  # NOTE: This disables ssl certificate verification
        self.subscription = None


    def update(self):
        """ Checks for new DMs and responds to valid requests """
        dms = self.get_dms()
        for event, cleartext in dms:
            self.process_request(event=event, decrypted_message=cleartext)


    def get_dms(self) -> List[Tuple[Event,str]]:
        """ Retrieves DMs and decrypts them. Should only retrieve new, never-before-seen
            DMs because:
            * ongoing Relay connections can only add new messages to the MessagePool.
            * Relay connections are initialized with the last_dm_request_created_at value.
        """
        # Store DMs keyed on sender; only keep the most recent one and whether we already responded
        dms = {}
        responded = []
        while self.relay_manager.message_pool.has_events():
            event_msg = self.relay_manager.message_pool.get_event()
            event = event_msg.event

            if event.public_key == self.settings.nostr_public_key_hex:
                # This is one of our own responses.
                # cleartext = self.settings.nostr_private_key.decrypt_message(event.content, event.pubkey_refs[0])
                # print(f"Reply to {PublicKey.from_hex(event.public_key).bech32()[:10]}: {cleartext}")

                # Our replies always reference the DM we're replying to; store that event_id
                responded.append(event.event_refs[0])
                continue

            try:
                print(f"From {PublicKey.from_hex(event.public_key).bech32()[:10]}: {event.content} | created_at: {event.created_at} | event_id: {event.id}")
                cleartext = self.settings.nostr_private_key.decrypt_message(encoded_message=event.content, public_key_hex=event.public_key)
            except ValueError:
                # The relays returned a DM that references us in a 'p' tag but is encrypted for someone else!
                print(f"Ignoring event_id {event.id} from {PublicKey.from_hex(event.public_key).bech32()[:10]}; can't decrypt")
                continue
            except Exception as e:
                print(e)
                continue

            if event.public_key not in dms or dms[event.public_key]["event"].created_at < event.created_at:
                # Update to the more recent Event
                print(f"Latest from {PublicKey.from_hex(event.public_key).bech32()[:10]}: {event.id} ({event.created_at})")
                dms[event.public_key] = dict(event=event, cleartext=cleartext)

            print(f"{PublicKey.from_hex(event.public_key).bech32()}: {cleartext}")

        if dms:
            print(dms)
        if responded:
            print(responded)

        # Have we already responded to any of these DMs?
        try:
            for event_id in responded:
                for pubkey, dm_dict in dms.items():
                    if dm_dict["event"].id == event_id:
                        print(f"Already responded to {PublicKey.from_hex(pubkey).bech32()[:10]} / {event_id}")
                        dm_dict["has_responded"] = True
                        break
        except Exception as e:
            import traceback, sys
            traceback.print_exc(file=sys.stdout)
        
        return [(d["event"], d["cleartext"]) for d in dms.values() if "has_responded" not in d]
    

    def process_request(self, event: Event, decrypted_message: str) -> str:
        print(f"Preparing reply to {PublicKey.from_hex(event.public_key).bech32()[:10]} / {event.id}")
        if decrypted_message.strip().lower().startswith("address"):
            # User requested a new onchain addr
            cleartext_content = self.get_next_address()
        else:
            cleartext_content = self.settings.campaign_message + """\n\nIf you'd like to make an onchain donation, just DM me the word: "address" """
        self.send_dm(recipient_pubkey=event.public_key, event_id=event.id, cleartext_content=cleartext_content)
        
        if self.settings.last_dm_processed is None or self.settings.last_dm_processed < event.created_at:
            print(f"Updating last_dm_processed to {event.created_at}")
            self.settings.set_last_dm_processed(event.created_at)


    """********************************************************************************************
                    Bitcoin operations
    ********************************************************************************************"""
    def get_next_address(self, type="p2wpkh") -> str:
        xpub = bip32.HDKey.from_string(self.settings.bitcoin_xpub)

        if type == "p2wpkh":
            addr = script.p2wpkh(xpub.derive(f"0/{self.settings.cur_child_index}")).address()

        elif type == "p2tr":
            addr = script.p2tr(xpub.derive(f"0/{self.settings.cur_child_index}")).address()
        
        else:
            raise Exception(f"Not yet implemented: address type {type}")

        self.settings.increment_child_index()

        return addr


    """********************************************************************************************
                    Nostr integration
    ********************************************************************************************"""
    def connect_relays(self):
        """ Connect to relays and subscribe to DM events """
        since = self.settings.last_dm_processed
        if since is not None:
            # Bump the timestamp so we don't replay the last DM
            since += 1

        filters = Filters([
            # DMs sent to this NostrPay identity...
            Filter(pubkey_refs=[self.settings.nostr_public_key_hex], kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE], since=self.settings.last_dm_processed),

            # ...and DMs sent from this NostrPay identity
            Filter(authors=[self.settings.nostr_public_key_hex], kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE], since=self.settings.last_dm_processed),
        ])
        self.subscription = Subscription(filters=filters)
        
        for relay in self.settings.relays:
            self.relay_manager.add_relay(relay)

        self.relay_manager.add_subscription(self.subscription)
        self.relay_manager.open_connections()
        time.sleep(1.25) # allow the connections to open

        # Send our subscription to the relays to begin indexing
        message = self.subscription.to_message()
        self.relay_manager.publish_message(message)
        time.sleep(1) # allow the messages to send


    def disconnect_relays(self):
        self.relay_manager.close_connections()
    

    def send_dm(self, recipient_pubkey: str, event_id: str, cleartext_content: str):
        dm = EncryptedDirectMessage(
            recipient_pubkey=recipient_pubkey,
            cleartext_content=cleartext_content,
            reference_event_id=event_id,
        )
        self.settings.nostr_private_key.sign_event(dm)
        self.relay_manager.publish_event(dm)