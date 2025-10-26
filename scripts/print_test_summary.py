#!/usr/bin/env python3

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: print_test_summary.py <pytest_rc> <junit_xml> <cov_xml>",
            file=sys.stderr,
        )
        sys.exit(1)

    pytest_rc = int(sys.argv[1])
    junit = Path(sys.argv[2])
    cov = Path(sys.argv[3])

    total = passed = 0
    pct = 0

    try:
        root = ET.parse(junit).getroot()
        suites = (
            [root]
            if root.tag == "testsuite"
            else list(root.findall("testsuite")) or list(root)
        )
        total = sum(int(s.attrib.get("tests", 0)) for s in suites)
        failed = sum(
            int(s.attrib.get("failures", 0)) + int(s.attrib.get("errors", 0))
            for s in suites
        )
        passed = max(0, total - failed)
    except Exception:
        print("0/0 test cases passed. 0% line coverage achieved.")
        sys.exit(1)

    try:
        croot = ET.parse(cov).getroot()
        if croot.attrib.get("line-rate") is not None:
            pct = round(float(croot.attrib["line-rate"]) * 100)
    except Exception:
        pass

    print(f"{passed}/{total} test cases passed. {pct}% line coverage achieved.")
    sys.exit(0 if (pytest_rc == 0 and cov.exists()) else 1)


if __name__ == "__main__":
    main()
