"""Owned temporary fixture HTTP process; callable only with harness guard."""
import argparse
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

if __name__=="__main__":
    if os.environ.get("HS2_HARNESS_GUARD")!="1":raise SystemExit("Run through credential-free fixture harness only")
    parser=argparse.ArgumentParser();parser.add_argument("--port-file",required=True);parser.add_argument("--port",type=int,default=0)
    args=parser.parse_args();p=Path(args.port_file)
    if not str(p).startswith("/tmp/hs2-"):raise SystemExit("Owned temporary fixture only")
    if os.environ.get("HS2_FIXTURE_SCREEN") == "supermap":
        from hs2_supermap.fixture_http import server
    elif os.environ.get("HS2_FIXTURE_SCREEN") == "calendar":
        from hs2_calendar.fixture_http import server
    elif os.environ.get("HS2_FIXTURE_SCREEN") == "listings":
        from hs2_listings.fixture_http import server
    elif os.environ.get("HS2_FIXTURE_SCREEN") == "consumer":
        from hs2_consumer.fixture_http import server
    elif os.environ.get("HS2_FIXTURE_SCREEN") == "mode":
        from hs2_modes.fixture_http import server
    else:
        from hs2_registration.fixture_http import server
    with server(args.port) as http:
        p.write_text(str(http.server_port))
        http.serve_forever()
