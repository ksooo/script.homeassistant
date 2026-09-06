#!/usr/bin/env python3
"""Names the supported_features bits this addon does not know about.

Home Assistant extends its EntityFeature enums without announcing it, and the
addon cannot notice on its own: an unknown bit is simply a command that is
never offered. Bits the addon has looked at and passed over are declared in
actions.IGNORED_FEATURES, so what is left really is new. Run this against a
real installation after an update.

    python3 tools/unknown_features.py https://homeassistant.example.com <token>

The address and token may also come from HA_URL and HA_TOKEN.
"""

import os
import sys

ADDON = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ADDON)

from resources.lib import actions, model  # noqa: E402  (path set up above)
from resources.lib.ha import auth as ha_auth  # noqa: E402
from resources.lib.ha import client as ha_client  # noqa: E402


def bits_of(mask):
    bit = 1
    while bit <= mask:
        if mask & bit:
            yield bit
        bit <<= 1


def unknown(mask, known):
    return [bit for bit in bits_of(mask) if not bit & known]


def states_of(url, token):
    client = ha_client.HomeAssistant(url, ha_auth.Authenticator(url, token=token))
    client.connect()
    try:
        return [model.State(payload) for payload in client.command("get_states")]
    finally:
        client.close()


def main(argv):
    url = (argv[1] if len(argv) > 1 else os.environ.get("HA_URL", "")).rstrip("/")
    token = argv[2] if len(argv) > 2 else os.environ.get("HA_TOKEN", "")
    if not url or not token:
        sys.stderr.write(__doc__)
        return 2

    states = states_of(url, token)

    findings = {}
    untouched = {}
    for state in states:
        mask = state.attributes.get("supported_features") or 0
        if not mask:
            continue
        known = actions.KNOWN_FEATURES.get(state.domain)
        if known is None:
            untouched.setdefault(state.domain, set()).add(mask)
            continue
        missing = unknown(mask, known | actions.IGNORED_FEATURES.get(state.domain, 0))
        if missing:
            findings.setdefault(state.domain, []).append((state.entity_id, mask, missing))

    for domain in sorted(findings):
        print(domain)
        for entity_id, mask, missing in sorted(findings[domain]):
            print("  %-46s features=%-7d unknown: %s"
                  % (entity_id, mask,
                     ", ".join("%d (bit %d)" % (bit, bit.bit_length() - 1)
                               for bit in missing)))
    if not findings:
        print("%d entities, no unknown feature bits" % len(states))

    if untouched:
        # Not a fault: plenty of domains are a plain switch here on purpose.
        # Worth a look all the same, because this is where the next command
        # people ask for will come from.
        print()
        print("domains reporting features that the addon offers no commands for:")
        for domain in sorted(untouched):
            print("  %-22s %s" % (domain, ", ".join(str(mask)
                                                    for mask in sorted(untouched[domain]))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
