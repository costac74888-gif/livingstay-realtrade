"""Real application HTTP on a parent-owned port; never a preview/live server."""
import argparse
from pathlib import Path
from werkzeug.serving import make_server
import app
from flask import Response


@app.app.route("/__offline__/photo.svg")
def fixture_photo():
    return Response('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240">'
                    '<rect width="320" height="240" fill="#dce7df"/>'
                    '<text x="24" y="120">OWNED SYNTHETIC PHOTO</text></svg>',
                    mimetype="image/svg+xml")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port-file", type=Path, required=True)
    args = parser.parse_args()
    server = make_server("127.0.0.1", 0, app.app, threaded=True)
    args.port_file.write_text(str(server.server_port))
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
