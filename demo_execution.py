import json
from datetime import datetime, timezone
from delta_demo import DeltaDemo
from store import get_signal, update_signal

def submit_approved_demo_entry(signal_id, product_symbol, contract_size, typed_confirmation):
    if typed_confirmation != "SUBMIT DEMO":
        raise ValueError("Type SUBMIT DEMO exactly to confirm the Demo order.")
    signal = get_signal(signal_id)
    if not signal:
        raise ValueError("Signal not found.")
    if signal["status"] != "PENDING_APPROVAL":
        raise ValueError("Signal is no longer pending approval.")
    created = datetime.fromisoformat(signal["created_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if age > 180:
        update_signal(signal_id, "EXPIRED", "Signal older than 180 seconds; generate a fresh signal.")
        raise ValueError("Signal expired. Do not submit stale entries.")
    if product_symbol != signal["symbol"]:
        raise ValueError("Selected Demo product symbol does not match the signal.")
    side = "buy" if signal["side"] == "long" else "sell"
    update_signal(signal_id, "APPROVED_SUBMITTING", "Explicit dashboard approval received.")
    try:
        client = DeltaDemo()
        response = client.place_market_entry(
            product_symbol, int(contract_size), side, "smc-v3-signal-" + str(signal_id)
        )
        update_signal(signal_id, "DEMO_ENTRY_SUBMITTED", "Demo entry order submitted.", json.dumps(response)[:3000])
        return response
    except Exception as exc:
        update_signal(signal_id, "SUBMISSION_ERROR", str(exc)[:1000])
        raise
