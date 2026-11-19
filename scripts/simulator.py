"""
FraudShield AI - Synthetic Transaction Simulator (PART 13.4, Week 11 Day 3-4)
=================================================================================
Standalone script that POSTs synthetic transactions to
POST /api/v1/transactions/predict every few seconds, using a small pool of
synthetic users/devices/locations, with 6 explicit scenario generators:

  normal | suspicious | high_value | rapid_repeated | new_device | unusual_location

ACADEMIC DISCLAIMER: every user_id, device_id, amount and location here is
fabricated. This script must NEVER be pointed at a real payment processor
or used with real card data.

Usage:
    python scripts/simulator.py --base-url http://localhost:8000 \\
        --email admin@fraudshield.ai --password StrongPass123! \\
        --interval 3 --count 50
"""
import argparse
import random
import sys
import time

import httpx

KNOWN_USERS = list(range(1, 11))          # a small pool of synthetic users
KNOWN_DEVICES = {u: f"dev-user{u}-primary" for u in KNOWN_USERS}
KNOWN_LOCATIONS = ["Mumbai", "Delhi", "Bengaluru", "Pune", "Chennai", "Hyderabad"]
UNUSUAL_LOCATIONS = ["Lagos", "Minsk", "Unknown-VPN-Exit", "Reykjavik"]

SCENARIOS = [
    "normal", "suspicious", "high_value",
    "rapid_repeated", "new_device", "unusual_location", "card_testing", "account_takeover", "transaction_splitting", "fraud_ring",
]

# Attack-style scenarios; everything else is ordinary customer behaviour. Real card/UPI fraud in
# Asia is a few percent of volume, so attacks are drawn only `--fraud-rate` of the time (3%).
ATTACK_SCENARIOS = ["suspicious", "card_testing", "account_takeover", "transaction_splitting", "fraud_ring"]
LEGIT_SCENARIOS = ["normal"] * 22 + ["high_value", "new_device", "rapid_repeated", "unusual_location"]


def pick_scenario(fraud_rate: float) -> str:
    return random.choice(ATTACK_SCENARIOS if random.random() < fraud_rate else LEGIT_SCENARIOS)


def get_token(base_url: str, email: str, password: str) -> str:
    resp = httpx.post(f"{base_url}/api/v1/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        # First run: the demo admin account may not exist yet -- register it.
        httpx.post(f"{base_url}/api/v1/auth/register",
                   json={"email": email, "password": password, "role": "admin"})
        resp = httpx.post(f"{base_url}/api/v1/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def build_payload(scenario: str) -> dict:
    user_id = random.choice(KNOWN_USERS)

    if scenario == "normal":
        return {
            "user_id": user_id, "amount": round(random.uniform(50, 2000), 2),
            "device_id": KNOWN_DEVICES[user_id], "location": random.choice(KNOWN_LOCATIONS),
            "payment_method": "card",
        }
    if scenario == "suspicious":
        return {
            "user_id": user_id, "amount": round(random.uniform(5000, 20000), 2),
            "device_id": f"dev-suspicious-{random.randint(1000,9999)}",
            "location": random.choice(UNUSUAL_LOCATIONS), "payment_method": "card",
        }
    if scenario == "high_value":
        return {
            "user_id": user_id, "amount": round(random.uniform(50000, 200000), 2),
            "device_id": KNOWN_DEVICES[user_id], "location": random.choice(KNOWN_LOCATIONS),
            "payment_method": "card",
        }
    if scenario == "rapid_repeated":
        # Caller is expected to send 3+ of these back-to-back for the same user/device.
        return {
            "user_id": user_id, "amount": round(random.uniform(1000, 10000), 2),
            "device_id": KNOWN_DEVICES[user_id], "location": random.choice(KNOWN_LOCATIONS),
            "payment_method": "card",
        }
    if scenario == "new_device":
        return {
            "user_id": user_id, "amount": round(random.uniform(1000, 30000), 2),
            "device_id": f"dev-new-{random.randint(10000,99999)}",
            "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    if scenario == "unusual_location":
        return {
            "user_id": user_id, "amount": round(random.uniform(500, 15000), 2),
            "device_id": KNOWN_DEVICES[user_id], "location": random.choice(UNUSUAL_LOCATIONS),
            "payment_method": "card",
        }
    if scenario == "card_testing":
        return {
            "user_id": user_id, "amount": round(random.choice([1,2,5,10,20,50]), 2),
            "device_id": KNOWN_DEVICES[user_id], "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    if scenario == "account_takeover":
        return {
            "user_id": user_id, "amount": round(random.uniform(20000, 90000), 2),
            "device_id": f"dev-takeover-{random.randint(10000,99999)}", "location": random.choice(UNUSUAL_LOCATIONS), "payment_method": "card",
        }
    if scenario == "transaction_splitting":
        return {
            "user_id": user_id, "amount": round(random.uniform(19000, 20000), 2),
            "device_id": KNOWN_DEVICES[user_id], "location": random.choice(KNOWN_LOCATIONS), "payment_method": "card",
        }
    if scenario == "fraud_ring":
        return {
            "user_id": user_id, "amount": round(random.uniform(8000, 30000), 2),
            "device_id": "shared-ring-device-01", "location": random.choice(UNUSUAL_LOCATIONS), "payment_method": "card",
        }
    raise ValueError(f"Unknown scenario: {scenario}")


def send_transaction(base_url: str, token: str, payload: dict) -> dict:
    resp = httpx.post(
        f"{base_url}/api/v1/transactions/predict",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def run(base_url: str, email: str, password: str, interval: float, count: int | None, fraud_rate: float = 0.03):
    token = get_token(base_url, email, password)
    print(f"[simulator] authenticated against {base_url}")

    sent = 0
    while count is None or sent < count:
        scenario = pick_scenario(fraud_rate)

        if scenario == "rapid_repeated":
            # fire 3 in quick succession, matching PART 13.4's definition.
            user_id = random.choice(KNOWN_USERS)
            for _ in range(3):
                payload = {
                    "user_id": user_id, "amount": round(random.uniform(1000, 10000), 2),
                    "device_id": KNOWN_DEVICES[user_id], "location": random.choice(KNOWN_LOCATIONS),
                    "payment_method": "card",
                }
                result = send_transaction(base_url, token, payload)
                print(f"[{scenario}] txn={result['transaction_id']} "
                      f"risk={result['risk_level']} score={result['risk_score']} "
                      f"decision={result['decision']}")
                sent += 1
                time.sleep(1)
        else:
            payload = build_payload(scenario)
            result = send_transaction(base_url, token, payload)
            print(f"[{scenario}] txn={result['transaction_id']} "
                  f"risk={result['risk_level']} score={result['risk_score']} "
                  f"decision={result['decision']}")
            sent += 1

        if count is not None and sent >= count:
            break
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FraudShield AI transaction simulator")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", default="admin@fraudshield.ai")
    parser.add_argument("--password", default="StrongPass123!")
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between transactions")
    parser.add_argument("--fraud-rate", type=float, default=0.03, help="share of transactions that are attacks (default 0.03 = 3%%)")
    parser.add_argument("--count", type=int, default=None, help="stop after N transactions (default: run forever)")
    args = parser.parse_args()

    try:
        run(args.base_url, args.email, args.password, args.interval, args.count, args.fraud_rate)
    except KeyboardInterrupt:
        print("\n[simulator] stopped by user")
        sys.exit(0)
