"""
FraudShield AI - Rate limiting (PART 14, Week 14 Day 2)
==========================================================
slowapi on /auth/login (prevent brute force) and /transactions/predict
(prevent flooding).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
