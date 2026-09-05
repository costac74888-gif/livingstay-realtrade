"""start-prod의 경량 분양 스키마 보장 (전체 init을 호출하지 않는다)."""
import os
import sys
import psycopg2

LOCK_KEY = 719240393
DDL = """
CREATE TABLE IF NOT EXISTS presale_projects (
 id BIGSERIAL PRIMARY KEY, master_building_id INTEGER NOT NULL UNIQUE REFERENCES master_buildings(id) ON DELETE RESTRICT,
 status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','withdrawn')),
 project_status TEXT NOT NULL DEFAULT 'presale' CHECK (project_status IN ('presale','scheduled','sold_out')),
 project_type TEXT NOT NULL DEFAULT 'mixed' CHECK (project_type IN ('living','tourist','officetel','mixed')),
 publication_start_at TIMESTAMPTZ, publication_end_at TIMESTAMPTZ, title TEXT NOT NULL, summary TEXT,
 unit_count INTEGER, remaining_units INTEGER, price_min BIGINT, price_max BIGINT, -- 가격은 만원(10,000 KRW) 단위
 sale_start_date DATE, sale_end_date DATE, move_in_date DATE,
 homepage_url TEXT, contact_name TEXT, contact_phone TEXT, company_name TEXT, editorial_body TEXT,
 applyhome_status TEXT NOT NULL DEFAULT 'unverified' CHECK (applyhome_status IN ('verified','unverified','not_applicable','error')),
 applyhome_notice_id TEXT, applyhome_notice_name TEXT, applyhome_checked_at TIMESTAMPTZ, applyhome_error_code TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 created_by INTEGER REFERENCES admin_users(id) ON DELETE SET NULL, updated_by INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
 withdrawn_at TIMESTAMPTZ, withdrawn_by INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
 CHECK (publication_end_at IS NULL OR publication_start_at IS NULL OR publication_end_at > publication_start_at),
 CHECK (sale_end_date IS NULL OR sale_start_date IS NULL OR sale_end_date >= sale_start_date),
 CHECK (unit_count IS NULL OR unit_count > 0), CHECK (remaining_units IS NULL OR (remaining_units >= 0 AND (unit_count IS NULL OR remaining_units <= unit_count))), CHECK (price_min IS NULL OR price_min >= 0),
 CHECK (price_max IS NULL OR price_max >= 0), CHECK (price_max IS NULL OR price_min IS NULL OR price_max >= price_min));
CREATE TABLE IF NOT EXISTS presale_promotions (
 id BIGSERIAL PRIMARY KEY, presale_project_id BIGINT NOT NULL REFERENCES presale_projects(id) ON DELETE CASCADE,
 status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','withdrawn')),
 starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL, slogan TEXT NOT NULL, cta_url TEXT NOT NULL,
 banner_object_key TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0 CHECK (priority BETWEEN 0 AND 10000),
 approved_at TIMESTAMPTZ, approved_by INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 created_by INTEGER REFERENCES admin_users(id) ON DELETE SET NULL, updated_by INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
 CHECK (ends_at > starts_at));
CREATE TABLE IF NOT EXISTS presale_applications (
 id BIGSERIAL PRIMARY KEY, master_building_id INTEGER NOT NULL REFERENCES master_buildings(id) ON DELETE RESTRICT,
 status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','reviewing','approved','rejected')),
 project_id BIGINT REFERENCES presale_projects(id) ON DELETE SET NULL,
 title TEXT NOT NULL, project_status TEXT NOT NULL CHECK (project_status IN ('presale','scheduled','sold_out')),
 project_type TEXT NOT NULL CHECK (project_type IN ('living','tourist','officetel','mixed')),
 summary TEXT, unit_count INTEGER, remaining_units INTEGER, price_min BIGINT, price_max BIGINT,
 sale_start_date DATE, sale_end_date DATE, move_in_date DATE,
 company_name TEXT NOT NULL, applicant_role TEXT, contact_name TEXT NOT NULL, contact_phone TEXT NOT NULL, contact_email TEXT NOT NULL,
 homepage_url TEXT, evidence_object_key TEXT NOT NULL, evidence_filename TEXT NOT NULL,
 banner_object_key TEXT, banner_filename TEXT, consent_version TEXT NOT NULL, consented_at TIMESTAMPTZ NOT NULL,
 receipt_notification_status TEXT NOT NULL DEFAULT 'pending' CHECK (receipt_notification_status IN ('pending','sent','failed')),
 decision_notification_status TEXT NOT NULL DEFAULT 'pending' CHECK (decision_notification_status IN ('pending','sent','failed')),
 notification_error TEXT,
 applyhome_status TEXT NOT NULL DEFAULT 'unverified' CHECK (applyhome_status IN ('verified','unverified','not_applicable','error')),
 applyhome_notice_id TEXT, applyhome_notice_name TEXT, applyhome_checked_at TIMESTAMPTZ, applyhome_error_code TEXT,
 reject_reason TEXT, reviewed_at TIMESTAMPTZ, reviewed_by INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CHECK (unit_count IS NULL OR unit_count > 0),
 CHECK (remaining_units IS NULL OR (remaining_units >= 0 AND (unit_count IS NULL OR remaining_units <= unit_count))),
 CHECK (price_min IS NULL OR price_min >= 0), CHECK (price_max IS NULL OR price_max >= 0),
 CHECK (price_max IS NULL OR price_min IS NULL OR price_max >= price_min),
 CHECK (sale_end_date IS NULL OR sale_start_date IS NULL OR sale_end_date >= sale_start_date));
CREATE TABLE IF NOT EXISTS presale_audit_log (
 id BIGSERIAL PRIMARY KEY, project_id BIGINT REFERENCES presale_projects(id) ON DELETE SET NULL,
 promotion_id BIGINT REFERENCES presale_promotions(id) ON DELETE SET NULL, application_id BIGINT REFERENCES presale_applications(id) ON DELETE SET NULL,
 admin_id INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
 action TEXT NOT NULL, detail JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE INDEX IF NOT EXISTS idx_presale_projects_public ON presale_projects(status, publication_start_at, publication_end_at);
CREATE INDEX IF NOT EXISTS idx_presale_promotions_active ON presale_promotions(presale_project_id,status,starts_at,ends_at,priority DESC);
CREATE INDEX IF NOT EXISTS idx_presale_applications_review ON presale_applications(status,created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_presale_applications_active_building ON presale_applications(master_building_id) WHERE status IN ('submitted','reviewing');
CREATE INDEX IF NOT EXISTS idx_presale_audit_project ON presale_audit_log(project_id,created_at DESC);
ALTER TABLE presale_audit_log ADD COLUMN IF NOT EXISTS application_id BIGINT REFERENCES presale_applications(id) ON DELETE SET NULL;
ALTER TABLE presale_applications ADD COLUMN IF NOT EXISTS receipt_notification_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE presale_applications ADD COLUMN IF NOT EXISTS decision_notification_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE presale_applications ADD COLUMN IF NOT EXISTS notification_error TEXT;
ALTER TABLE presale_applications ADD COLUMN IF NOT EXISTS applicant_role TEXT;
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS homepage_url TEXT;
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS project_status TEXT NOT NULL DEFAULT 'presale';
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS project_type TEXT NOT NULL DEFAULT 'mixed';
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS remaining_units INTEGER;
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS move_in_date DATE;
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS applyhome_status TEXT NOT NULL DEFAULT 'unverified';
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS applyhome_notice_id TEXT;
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS applyhome_notice_name TEXT;
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS applyhome_checked_at TIMESTAMPTZ;
ALTER TABLE presale_projects ADD COLUMN IF NOT EXISTS applyhome_error_code TEXT;
ALTER TABLE presale_applications ADD COLUMN IF NOT EXISTS applyhome_status TEXT NOT NULL DEFAULT 'unverified';
ALTER TABLE presale_applications ADD COLUMN IF NOT EXISTS applyhome_notice_id TEXT;
ALTER TABLE presale_applications ADD COLUMN IF NOT EXISTS applyhome_notice_name TEXT;
ALTER TABLE presale_applications ADD COLUMN IF NOT EXISTS applyhome_checked_at TIMESTAMPTZ;
ALTER TABLE presale_applications ADD COLUMN IF NOT EXISTS applyhome_error_code TEXT;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='presale_projects_project_status_check') THEN
  ALTER TABLE presale_projects ADD CONSTRAINT presale_projects_project_status_check CHECK (project_status IN ('presale','scheduled','sold_out')) NOT VALID;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='presale_projects_project_type_check') THEN
  ALTER TABLE presale_projects ADD CONSTRAINT presale_projects_project_type_check CHECK (project_type IN ('living','tourist','officetel','mixed')) NOT VALID;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='presale_projects_remaining_units_check') THEN
  ALTER TABLE presale_projects ADD CONSTRAINT presale_projects_remaining_units_check CHECK (remaining_units IS NULL OR (remaining_units >= 0 AND (unit_count IS NULL OR remaining_units <= unit_count))) NOT VALID;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='presale_projects_applyhome_status_check') THEN
  ALTER TABLE presale_projects ADD CONSTRAINT presale_projects_applyhome_status_check CHECK (applyhome_status IN ('verified','unverified','not_applicable','error')) NOT VALID;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='presale_applications_applyhome_status_check') THEN
  ALTER TABLE presale_applications ADD CONSTRAINT presale_applications_applyhome_status_check CHECK (applyhome_status IN ('verified','unverified','not_applicable','error')) NOT VALID;
 END IF;
END $$;
"""
def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor(); cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,)); cur.execute(DDL); conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
if __name__ == "__main__":
    try: main()
    except Exception as exc: print(f"presale schema failed: {exc}", file=sys.stderr); sys.exit(1)