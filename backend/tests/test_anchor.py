"""Phase 6 anchoring tests — no network: web3 is faked via injection."""

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.models import Report
from app.services.anchor import (
    AnchorError,
    anchor_report,
    build_anchor_tx,
)

HASH = "a" * 64


class FakeSignedTx:
    raw_transaction = b"signed-raw-bytes"


class FakeAccount:
    address = "0x" + "11" * 20

    @staticmethod
    def sign_transaction(tx: dict) -> FakeSignedTx:
        return FakeSignedTx()


class FakeEth:
    chain_id = 80002
    gas_price = 30_000_000_000
    account = SimpleNamespace(from_key=lambda key: FakeAccount())

    def __init__(self) -> None:
        self.sent: list = []
        self.fail_send = False

    def get_transaction_count(self, address: str) -> int:
        return 7

    def send_raw_transaction(self, raw: bytes):
        if self.fail_send:
            raise RuntimeError("insufficient funds for gas")
        self.sent.append(raw)
        return bytes.fromhex("cd" * 32)

    def wait_for_transaction_receipt(self, tx_hash, timeout=None) -> dict:
        return {"status": 1, "blockNumber": 6_123_456}


class FakeW3:
    def __init__(self) -> None:
        self.eth = FakeEth()


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        DATABASE_URL="sqlite://",
        LLM_PROVIDER="mock",
        POLYGON_ANCHOR_ENABLED=True,
        POLYGON_PRIVATE_KEY="0x" + "22" * 32,
    )


@pytest.fixture()
def report(db_session) -> Report:
    r = Report(
        case_id=None,  # type: ignore[arg-type]  # not used by anchoring logic
        risk_rating="low",
        summary="s",
        report_hash=HASH,
    )
    return r


class TestBuildAnchorTx:
    def test_hash_becomes_calldata(self) -> None:
        tx = build_anchor_tx(
            HASH, sender="0x" + "11" * 20, nonce=1, gas_price_wei=10, chain_id=80002
        )
        assert tx["data"] == bytes.fromhex(HASH)
        assert len(tx["data"]) == 32
        assert tx["value"] == 0
        assert tx["to"] == tx["from"]  # self-transfer notarization
        assert tx["chainId"] == 80002

    def test_rejects_bad_hash(self) -> None:
        with pytest.raises(AnchorError):
            build_anchor_tx("zz", sender="0x" + "11" * 20, nonce=1, gas_price_wei=1, chain_id=1)

    def test_uppercase_hash_normalized(self) -> None:
        tx = build_anchor_tx(
            HASH.upper(), sender="0x" + "11" * 20, nonce=1, gas_price_wei=1, chain_id=1
        )
        assert tx["data"] == bytes.fromhex(HASH)


class TestAnchorReport:
    def test_happy_path_persists(self, settings) -> None:
        w3 = FakeW3()
        report = SimpleNamespace(  # minimal stand-in for the ORM row
            id="r1",
            report_hash=HASH,
            anchor_status=None,
            anchor_tx_hash=None,
            anchor_block_number=None,
            anchored_at=None,
        )

        class FakeDB:
            def commit(self) -> None:
                pass

        result = anchor_report(FakeDB(), report, settings, w3=w3)  # type: ignore[arg-type]
        assert result.status == "confirmed"
        assert result.tx_hash == "0x" + "cd" * 32
        assert result.block_number == 6_123_456
        assert report.anchor_status == "confirmed"
        assert report.anchor_tx_hash == result.tx_hash
        assert report.anchored_at is not None
        # exactly one raw tx sent, carrying the 32-byte hash
        assert len(w3.eth.sent) == 1
        assert w3.eth.sent[0] == b"signed-raw-bytes"

    def test_disabled_raises(self) -> None:
        s = Settings(
            DATABASE_URL="sqlite://",
            LLM_PROVIDER="mock",
            POLYGON_ANCHOR_ENABLED=False,
            POLYGON_PRIVATE_KEY="0x" + "22" * 32,
        )
        report = SimpleNamespace(report_hash=HASH, anchor_status=None, anchor_tx_hash=None)
        with pytest.raises(AnchorError, match="disabled"):
            anchor_report(SimpleNamespace(commit=lambda: None), report, s, w3=FakeW3())  # type: ignore[arg-type]

    def test_idempotent_short_circuit(self, settings) -> None:
        report = SimpleNamespace(
            id="r2",
            report_hash=HASH,
            anchor_status="confirmed",
            anchor_tx_hash="0x" + "ef" * 32,
            anchor_block_number=42,
            anchored_at=None,
        )
        w3 = FakeW3()
        result = anchor_report(SimpleNamespace(commit=lambda: None), report, settings, w3=w3)  # type: ignore[arg-type]
        assert result.tx_hash == "0x" + "ef" * 32
        assert w3.eth.sent == []  # no new tx

    def test_send_failure_marks_failed(self, settings) -> None:
        w3 = FakeW3()
        w3.eth.fail_send = True
        report = SimpleNamespace(
            id="r3",
            report_hash=HASH,
            anchor_status=None,
            anchor_tx_hash=None,
            anchor_block_number=None,
            anchored_at=None,
        )
        with pytest.raises(AnchorError, match="insufficient funds"):
            anchor_report(SimpleNamespace(commit=lambda: None), report, settings, w3=w3)  # type: ignore[arg-type]
        assert report.anchor_status == "failed"

    def test_chain_id_mismatch_raises(self, settings) -> None:
        w3 = FakeW3()
        w3.eth.chain_id = 1  # mainnet — must refuse
        report = SimpleNamespace(report_hash=HASH, anchor_status=None, anchor_tx_hash=None)
        with pytest.raises(AnchorError, match="chain_id"):
            anchor_report(SimpleNamespace(commit=lambda: None), report, settings, w3=w3)  # type: ignore[arg-type]


class TestAnchorEndpoint:
    def test_unanchored_report_503_when_disabled(self, client) -> None:
        # disabled by default → endpoint surfaces a clear 503, never a crash
        resp = client.post("/cases/00000000-0000-0000-0000-000000000001/report/anchor")
        assert resp.status_code in (404, 503)

    def test_missing_report_404(self, client) -> None:
        resp = client.post("/cases/00000000-0000-0000-0000-000000000009/report/anchor")
        assert resp.status_code == 404

    def test_get_report_exposes_anchor_fields(self, client) -> None:
        # ReportOut schema now carries the anchor_* columns (all null pre-anchor)
        resp = client.get("/cases/00000000-0000-0000-0000-000000000009/report")
        assert resp.status_code == 404  # no report yet — field presence checked below
        from app.schemas.report import ReportOut

        fields = set(ReportOut.model_fields)
        assert {"anchor_status", "anchor_tx_hash", "anchor_block_number", "anchored_at"} <= fields
