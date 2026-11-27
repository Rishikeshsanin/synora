"""Fail if pytest did not execute tests or skipped any required cases."""
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
cases = list(root.iter("testcase"))
assert cases, "No tests executed"
assert not any(case.find("skipped") is not None for case in cases), "Required tests skipped"
assert not any(case.find(tag) is not None for case in cases for tag in ("failure", "error")), "Failed cases"
print(f"Verified {len(cases)} executed test cases, zero skips")
