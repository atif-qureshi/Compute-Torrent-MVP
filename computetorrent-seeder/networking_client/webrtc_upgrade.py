"""
WebRTC STUN Upgrade — NC-4
Attempts a STUN handshake for a direct peer-to-peer WebRTC connection.
On any failure (no STUN server reachable, timeout, exception) it falls
back to the WebSocket relay silently — no user-facing error, per NC-4.

MVP scope: STUN reachability probe only (UDP ping to stun.l.google.com).
Full ICE/DTLS negotiation is out of scope for the MVP.
"""

from __future__ import annotations

import logging
import socket
import struct

logger = logging.getLogger("computetorrent.networking_client.webrtc_upgrade")

STUN_HOST = "stun.l.google.com"
STUN_PORT = 19302
STUN_TIMEOUT_S = 3


def attempt_stun_upgrade(stun_host: str = STUN_HOST, stun_port: int = STUN_PORT,
                          timeout: float = STUN_TIMEOUT_S) -> bool:
    """
    Send a minimal STUN Binding Request and check we get any response back.
    Returns True if a direct path looks plausible; False on any failure.
    Never raises — silently returns False so the caller stays on the relay.

    RFC 5389 §6: a Binding Request is a 20-byte header with:
      - Message Type:   0x0001 (Binding Request)
      - Message Length: 0x0000 (no attributes)
      - Magic Cookie:   0x2112A442
      - Transaction ID: 12 random bytes
    """
    try:
        import os
        transaction_id = os.urandom(12)
        msg = struct.pack(">HHI", 0x0001, 0x0000, 0x2112A442) + transaction_id

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(msg, (stun_host, stun_port))
            data, _ = sock.recvfrom(512)
            # Any response ≥ 20 bytes with magic cookie confirms STUN reachability
            if len(data) >= 20:
                cookie = struct.unpack(">I", data[4:8])[0]
                if cookie == 0x2112A442:
                    logger.info("STUN probe succeeded — direct WebRTC path available.")
                    return True
        logger.info("STUN response invalid — falling back to relay.")
        return False
    except Exception as exc:
        logger.info("STUN probe failed (%s) — falling back to relay.", exc)
        return False
