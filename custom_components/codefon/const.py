"""Constants of the Codefon integration."""

DOMAIN = "codefon"

CONF_TOKEN = "token"
CONF_DEVICE_ID = "device_id"
CONF_WS_PORT = "ws_port"

PAIR_LABEL = "Home Assistant"

STATES = ["idle", "ringing", "talking", "line_down"]

# The device's event_type values (lib/codefon_core/include/codefon/event_json.h).
EVENT_TYPES = [
    "ring",
    "answered",
    "canceled",
    "unanswered",
    "talk_ended",
    "no_handset",
    "entry",
    "entry_denied",
    "door",
    "door_hung_up",
    "audio",
    "code_entry",
    "code_wrong",
    "card_entry",
    "card_unknown",
    "service_code",
    "eeprom_write",
    "supply_lost",
    "supply_back",
    "line_fault",
    "logger_restart",
    "logger_ring",
]
