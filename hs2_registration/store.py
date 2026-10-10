"""Write ONLY the Phase 2 reference layer, ONLY in an owned PostgreSQL fixture."""
from uuid import uuid4
from hs2_data.repository import require_fixture
from hs2_design.domain import ContractError


class PostgresReferenceStore:
    def __init__(self, conn):
        require_fixture(conn)
        self.conn=conn

    def legacy(self, identity):
        require_fixture(self.conn)
        with self.conn.cursor() as c:
            c.execute("SELECT id,identity_key FROM hs2_fixture_legacy.master_buildings WHERE identity_key=%s",(identity,))
            return [dict(id=r[0],identity_key=r[1]) for r in c.fetchall()]

    def save(self, building, coordinates, master_id):
        require_fixture(self.conn)
        with self.conn.cursor() as c:
            c.execute("SAVEPOINT hs2_reference")
            try:
                identity=building["identity_key"]
                c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(identity,))
                values=(building["road_address"],building["building_use"],coordinates["lat"],coordinates["lng"])
                c.execute("SELECT id,road_address,building_use,lat,lng FROM hs2_dev.candidates WHERE identity_confirmed AND identity_key=%s",(identity,))
                existing=c.fetchone()
                if existing:
                    if (existing[1],existing[2],float(existing[3]) if existing[3] is not None else None,
                        float(existing[4]) if existing[4] is not None else None)!=values:
                        raise ContractError("REFERENCE_CONFLICT")
                    ref=existing[0]
                else:
                    ref=uuid4()
                    c.execute("""INSERT INTO hs2_dev.candidates
                     (id,identity_key,identity_confirmed,road_address,building_use,lat,lng,evidence_version)
                     VALUES(%s,%s,true,%s,%s,%s,%s,%s)""",
                     (str(ref),identity,*values,building["evidence_version"]+";"+coordinates["evidence_version"]))
                c.execute("SELECT master_id FROM hs2_dev.master_links WHERE candidate_id=%s",(str(ref),))
                link=c.fetchone()
                if link:
                    if link[0]!=master_id:raise ContractError("LEGACY_LINK_CONFLICT")
                elif master_id is not None:
                    c.execute("INSERT INTO hs2_dev.master_links VALUES(%s,%s,%s,%s)",
                              (str(ref),master_id,identity,building["evidence_version"]))
                c.execute("RELEASE SAVEPOINT hs2_reference")
                return ref
            except BaseException:
                c.execute("ROLLBACK TO SAVEPOINT hs2_reference")
                c.execute("RELEASE SAVEPOINT hs2_reference")
                raise
