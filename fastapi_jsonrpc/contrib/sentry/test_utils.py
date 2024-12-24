from collections import Counter


def assert_jrpc_batch_sentry_items(envelops, expected_items):
    items = [item.type for e in envelops for item in e.items]
    actual_items = Counter(items)
    assert all(item in actual_items.items() for item in expected_items.items()), actual_items.items()
    transactions = get_captured_transactions(envelops)
    # same trace_id across jrpc batch
    trace_ids = set()
    for transaction in transactions:
        trace_ids.add(get_transaction_trace_id(transaction))

    assert len(trace_ids) == 1, trace_ids
    return actual_items


def get_transaction_trace_id(transaction):
    return transaction.payload.json["contexts"]["trace"]["trace_id"]


def get_captured_transactions(envelops):
    return [item for e in envelops for item in e.items if item.type == "transaction"]
