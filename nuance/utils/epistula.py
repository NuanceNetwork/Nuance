"""Epistula V2 protocol utilities with case-insensitive header handling"""
import json
import time
from hashlib import sha256
from uuid import uuid4
from math import ceil
from typing import Any, Optional

import bittensor as bt

ALLOWED_DELTA_MS = 8000  # 8 seconds

def get_header_case_insensitive(headers: dict, key: str) -> Optional[str]:
    """Get header value in a case-insensitive way"""
    # Try exact match first
    if key in headers:
        return headers[key]
    
    # Try lowercase
    key_lower = key.lower()
    if key_lower in headers:
        return headers[key_lower]
    
    # Try all variations
    for header_key, header_value in headers.items():
        if header_key.lower() == key_lower:
            return header_value
    
    return None

def create_request(
    data: dict[str, Any],
    sender_keypair: bt.Keypair,
    receiver_hotkey: Optional[str] = None
) -> tuple[bytes, dict[str, str]]:
    """
    Create signed request with Epistula V2 protocol.
    Returns (body_bytes, headers)
    """
    # Convert data to bytes
    body_bytes = json.dumps(data).encode("utf-8")
    
    # Generate timestamp and UUID
    timestamp = round(time.time() * 1000)
    timestamp_interval = ceil(timestamp / 1e4) * 1e4
    uuid_str = str(uuid4())
    
    # Create base headers
    headers = {
        "Epistula-Version": "2",
        "Epistula-Timestamp": str(timestamp),
        "Epistula-Uuid": uuid_str,
        "Epistula-Signed-By": sender_keypair.ss58_address,
        "Epistula-Request-Signature": "0x" + sender_keypair.sign(
            f"{sha256(body_bytes).hexdigest()}.{uuid_str}.{timestamp}.{receiver_hotkey or ''}"
        ).hex(),
    }
    
    # Add receiver-specific headers if signed for someone
    if receiver_hotkey:
        headers["Epistula-Signed-For"] = receiver_hotkey
        headers["Epistula-Secret-Signature-0"] = (
            "0x" + sender_keypair.sign(str(timestamp_interval - 1) + "." + receiver_hotkey).hex()
        )
        headers["Epistula-Secret-Signature-1"] = (
            "0x" + sender_keypair.sign(str(timestamp_interval) + "." + receiver_hotkey).hex()
        )
        headers["Epistula-Secret-Signature-2"] = (
            "0x" + sender_keypair.sign(str(timestamp_interval + 1) + "." + receiver_hotkey).hex()
        )
    
    return body_bytes, headers

def verify_request(
    headers: dict[str, str],
    body: bytes,
    metagraph: bt.metagraph,
    expected_receiver: Optional[str] = None
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Verify request signature with Epistula V2 protocol.
    Returns (is_valid, error_message, sender_hotkey)
    """
    try:
        # Extract headers using case-insensitive lookup
        signature = get_header_case_insensitive(headers, "Epistula-Request-Signature")
        timestamp = get_header_case_insensitive(headers, "Epistula-Timestamp")
        uuid_str = get_header_case_insensitive(headers, "Epistula-Uuid")
        signed_for = get_header_case_insensitive(headers, "Epistula-Signed-For") or ""
        signed_by = get_header_case_insensitive(headers, "Epistula-Signed-By")
        version = get_header_case_insensitive(headers, "Epistula-Version")
        
        # Check version
        if version != "2":
            return False, f"Unsupported Epistula version: {version}", None
        
        # Basic validation
        if not signature:
            return False, "Missing signature", None
        if not timestamp:
            return False, "Missing timestamp", None
        if not uuid_str:
            return False, "Missing UUID", None
        if not signed_by:
            return False, "Missing sender", None
            
        # Convert timestamp
        try:
            timestamp_int = int(timestamp)
        except Exception:
            return False, "Invalid timestamp", None
            
        # Check if sender in metagraph
        if signed_by not in metagraph.hotkeys:
            return False, "Sender not in metagraph", None
            
        # Check staleness
        now = round(time.time() * 1000)
        if timestamp_int + ALLOWED_DELTA_MS < now:
            return False, "Request too stale", None
            
        # Check expected receiver if specified
        if expected_receiver and signed_for and signed_for != expected_receiver:
            return False, "Request not signed for this receiver", None
            
        # Verify signature
        if signature.startswith("0x"):
            signature = signature[2:]
            
        keypair = bt.Keypair(ss58_address=signed_by)
        message = f"{sha256(body).hexdigest()}.{uuid_str}.{timestamp}.{signed_for}"
        
        if not keypair.verify(message, bytes.fromhex(signature)):
            return False, "Invalid signature", None
            
        return True, None, signed_by
        
    except Exception as e:
        return False, f"Verification error: {str(e)}", None

def verify_secret_signatures(
    headers: dict[str, str],
    receiver_keypair: bt.Keypair
) -> bool:
    """
    Verify secret signatures when request is signed for a specific receiver.
    This proves the sender knows who they're sending to.
    """
    try:
        timestamp = get_header_case_insensitive(headers, "Epistula-Timestamp")
        signed_by = get_header_case_insensitive(headers, "Epistula-Signed-By")
        signed_for = get_header_case_insensitive(headers, "Epistula-Signed-For")
        
        if not all([timestamp, signed_by, signed_for]):
            return False
            
        # Check if signed for us
        if signed_for != receiver_keypair.ss58_address:
            return False
            
        # Calculate timestamp interval
        timestamp_int = int(timestamp)
        timestamp_interval = ceil(timestamp_int / 1e4) * 1e4
        
        # Verify at least one secret signature
        sender_keypair = bt.Keypair(ss58_address=signed_by)
        
        for i, interval_offset in enumerate([-1, 0, 1]):
            sig_header = f"Epistula-Secret-Signature-{i}"
            signature = get_header_case_insensitive(headers, sig_header) or ""
            
            if signature.startswith("0x"):
                signature = signature[2:]
                
            message = f"{timestamp_interval + interval_offset}.{signed_for}"
            
            try:
                if sender_keypair.verify(message, bytes.fromhex(signature)):
                    return True
            except Exception:
                continue
                
        return False
        
    except Exception:
        return False
