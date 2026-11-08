#!/usr/bin/env python3
"""Demonstrate the original GLM TAP log assertion's prefix blind spot."""
import re

log = '2026-11-08 00:00:00.000 UTC [123] ERROR: STREAM ABORT message without STREAM STOP\n'
glm_detects_error = re.search(r'^ERROR:', log, re.MULTILINE | re.DOTALL) is not None
independent_detects_error = re.search(r'\b(?:ERROR|PANIC|FATAL):\s+(.*)$', log, re.MULTILINE) is not None
print('Original GLM expression detects the error:', glm_detects_error)
print('Independent expression detects the error:', independent_detects_error)
assert not glm_detects_error and independent_detects_error
