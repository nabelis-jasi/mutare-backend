# route_audit.py
# Run:  python route_audit.py
#
# Lists every registered URL rule and FAILS LOUDLY if any URL+method is
# registered by more than one view function. Flask does NOT warn about
# this - it silently serves whichever rule was registered first, which
# is exactly the bug that broke the manhole filters and the statistics
# charts in this project. Run this after adding any new route.

from collections import defaultdict
from app import app


def audit():
    seen = defaultdict(list)
    for rule in app.url_map.iter_rules():
        methods = sorted(m for m in rule.methods if m not in ('HEAD', 'OPTIONS'))
        for method in methods:
            seen[(rule.rule, method)].append(rule.endpoint)

    print(f"{'METHOD':7} {'URL':45} ENDPOINT (blueprint.function)")
    print("-" * 100)
    for (url, method), endpoints in sorted(seen.items()):
        flag = "  <-- DUPLICATE!" if len(endpoints) > 1 else ""
        print(f"{method:7} {url:45} {', '.join(endpoints)}{flag}")

    duplicates = {k: v for k, v in seen.items() if len(v) > 1}
    print("-" * 100)
    if duplicates:
        print(f"\n❌ {len(duplicates)} DUPLICATE registration(s) found:")
        for (url, method), endpoints in duplicates.items():
            print(f"   {method} {url}")
            print(f"      registered by: {', '.join(endpoints)}")
            print(f"      Flask will serve '{endpoints[0]}' and silently ignore the rest.")
        raise SystemExit(1)
    print(f"\n✅ {len(seen)} routes registered, no duplicates.")


if __name__ == '__main__':
    audit()
