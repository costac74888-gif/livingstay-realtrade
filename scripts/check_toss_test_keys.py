"""Report only configuration booleans; never print keys, lengths or digests.

This is not provider authentication, a payment integration or a merchant-pair
validation. No imports with app boot effects, network, database or delivery.
"""
import json
import os


def check(env):
    client = env.get("TOSS_TEST_CLIENT_KEY", "")
    secret = env.get("TOSS_TEST_SECRET_KEY", "")
    result = {
        "client_present": bool(client),
        "secret_present": bool(secret),
        "client_test_format": client.startswith("test_gck_"),
        "secret_test_format": secret.startswith("test_gsk_"),
        "client_document_example": client.startswith("test_gck_docs_"),
        "secret_document_example": secret.startswith("test_gsk_docs_"),
        "provider_called": False,
        "merchant_pair_verified": False,
    }
    result["ok"] = (
        result["client_present"] and result["secret_present"]
        and result["client_test_format"] and result["secret_test_format"]
        and not result["client_document_example"]
        and not result["secret_document_example"]
    )
    return result


if __name__ == "__main__":
    status = check(os.environ)
    print(json.dumps(status, sort_keys=True))
    raise SystemExit(0 if status["ok"] else 1)
