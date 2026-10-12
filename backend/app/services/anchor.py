"""Phase 6 — on-chain anchoring of report hashes on Polygon Amoy testnet.

Strategy: a zero-value self-transfer transaction whose calldata is the
report's SHA-256 hash (exactly 32 bytes). That writes the hash into an
immutable on-chain transaction; anyone can later verify report integrity by
re-hashing the canonical report JSON and comparing it with the tx calldata
on https://amoy.polygonscan.com/tx/<hash>.

Design notes:
- Dependency-light: `web3` is an OPTIONAL extra (`pip install '.[chain]'`),
  imported lazily so the rest of the app never needs it.
- `w3` is injectable for tests — the service's own logic (tx shape, state
  machine, persistence) is exercised with a fake client, no network.
- Idempotent: an already-anchored report short-circuits, never re-spending
  testnet gas.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Report

logger = logging.getLogger(__name__)

# Gas for a zero-value self-transfer with 32 bytes of calldata (~60k is ample
# on Polygon; the estimate below is also refreshed from the node when web3 is
# available, this is just the fallback).
DEFAULT_GAS_LIMIT = 60_000


class AnchorError(Exception):
    """Anchoring cannot proceed (config, network, or chain failure)."""


@dataclass(frozen=True)
class AnchorResult:
    tx_hash: str
    block_number: int
    status: str  # confirmed | failed
    chain_id: int
    explorer_url: str


def build_anchor_tx(
    report_hash: str,
    *,
    sender: str,
    nonce: int,
    gas_price_wei: int,
    chain_id: int,
    to: str | None = None,
    gas: int = DEFAULT_GAS_LIMIT,
) -> dict:
    """Pure tx-dict builder (no network) — deterministic and unit-testable.

    The report hash becomes the tx calldata: data == raw 32 bytes of the
    SHA-256 digest. Recipient defaults to self (simplest notarization).
    """
    digest = report_hash.strip().lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise AnchorError(f"report_hash must be 64 hex chars, got {report_hash!r}")
    return {
        "chainId": chain_id,
        "from": sender,
        "to": to or sender,
        "value": 0,
        "nonce": nonce,
        "gasPrice": gas_price_wei,
        "gas": gas,
        "data": bytes.fromhex(digest),
    }


def _require_web3(settings: Settings):
    """Lazily build a connected web3 client, or raise a clear AnchorError."""
    try:
        from web3 import Web3
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise AnchorError("web3 not installed — run: pip install '.[chain]'") from exc
    if not settings.polygon_private_key:
        raise AnchorError("POLYGON_PRIVATE_KEY not configured")
    w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise AnchorError(f"cannot reach Polygon RPC at {settings.polygon_rpc_url}")
    return w3


def anchor_report(db: Session, report: Report, settings: Settings, *, w3=None) -> AnchorResult:
    """Anchor report.report_hash on Polygon Amoy; persist status columns.

    `w3` is injectable for tests. Raises AnchorError on any failure — the
    report row records `failed` so reviewers can retry later.
    """
    if not settings.polygon_anchor_enabled:
        raise AnchorError("anchoring disabled — set POLYGON_ANCHOR_ENABLED=true")

    # Idempotency: never re-spend gas for an already-anchored report.
    if report.anchor_status == "confirmed" and report.anchor_tx_hash:
        return AnchorResult(
            tx_hash=report.anchor_tx_hash,
            block_number=report.anchor_block_number or 0,
            status="confirmed",
            chain_id=settings.polygon_chain_id,
            explorer_url=settings.polygon_explorer_tx_url + report.anchor_tx_hash,
        )

    w3 = w3 or _require_web3(settings)
    if w3.eth.chain_id != settings.polygon_chain_id:
        raise AnchorError(
            f"RPC reports chain_id={w3.eth.chain_id}, expected {settings.polygon_chain_id} "
            f"({settings.polygon_rpc_url})"
        )
    if not settings.polygon_private_key:
        raise AnchorError("POLYGON_PRIVATE_KEY not configured")
    account = w3.eth.account.from_key(settings.polygon_private_key)

    gas_price = w3.eth.gas_price
    tx = build_anchor_tx(
        report.report_hash,
        sender=account.address,
        nonce=w3.eth.get_transaction_count(account.address),
        gas_price_wei=gas_price,
        chain_id=settings.polygon_chain_id,
    )
    signed = account.sign_transaction(tx)

    report.anchor_status = "pending"
    db.commit()

    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    except Exception as exc:  # noqa: BLE001 — chain/network failures vary wildly
        report.anchor_status = "failed"
        db.commit()
        logger.error("anchor_failed report_id=%s err=%s", report.id, exc)
        raise AnchorError(f"anchor transaction failed: {exc}") from exc

    tx_hex = tx_hash.hex()
    tx_hex = tx_hex if tx_hex.startswith("0x") else f"0x{tx_hex}"
    ok = int(receipt.get("status", 0)) == 1
    result = AnchorResult(
        tx_hash=tx_hex,
        block_number=int(receipt.get("blockNumber", 0)),
        status="confirmed" if ok else "failed",
        chain_id=settings.polygon_chain_id,
        explorer_url=settings.polygon_explorer_tx_url + tx_hex,
    )

    report.anchor_status = result.status
    report.anchor_tx_hash = result.tx_hash
    report.anchor_block_number = result.block_number
    report.anchored_at = datetime.now(UTC)
    db.commit()
    logger.info(
        "anchor_%s report_id=%s tx=%s block=%d",
        result.status,
        report.id,
        result.tx_hash,
        result.block_number,
    )
    return result
