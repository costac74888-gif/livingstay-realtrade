"""Read-only PUBLIC fixture view reuse, not a live DB/migration default."""
from hs2_data.repository import require_fixture, FixtureRepository


class FixtureCatalog:
    def __init__(self, conn, quote):
        require_fixture(conn)
        self.conn, self.quote = conn, quote

    def __call__(self, values):
        with self.conn.cursor() as c:
            c.execute("SELECT public_id,stay_kind,location_precision FROM hs2_dev.limited_stay_listings")
            rows = [dict(public_id=str(r[0]), stay_kind=r[1], location_precision=r[2])
                    for r in c.fetchall()]
        for row in rows:
            if values["check_in"]:
                row["quote"] = self.quote(row["public_id"], values)
        return rows
