CREATE TABLE hs2_dev.stay_favorites(
 user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 public_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(user_id,public_id)
);
CREATE TABLE hs2_dev.stay_threads(
 id uuid PRIMARY KEY,
 application_id uuid NOT NULL REFERENCES hs2_dev.registration_applications(id),
 consumer_user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 operator_user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 operator_context_id text NOT NULL,
 booking_id uuid REFERENCES hs2_dev.bookings(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX one_listing_inquiry ON hs2_dev.stay_threads(application_id,consumer_user_id)
 WHERE booking_id IS NULL;
CREATE UNIQUE INDEX one_booking_chat ON hs2_dev.stay_threads(booking_id) WHERE booking_id IS NOT NULL;
CREATE TABLE hs2_dev.stay_messages(
 id uuid PRIMARY KEY,
 thread_id uuid NOT NULL REFERENCES hs2_dev.stay_threads(id),
 sender_user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 request_id uuid NOT NULL,
 request_hash text NOT NULL,
 body text NOT NULL CHECK(length(body) BETWEEN 1 AND 2000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(sender_user_id,request_id)
);
CREATE TABLE hs2_dev.stay_thread_reads(
 thread_id uuid NOT NULL REFERENCES hs2_dev.stay_threads(id),
 user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 through_at timestamptz NOT NULL,
 through_message_id uuid NOT NULL,
 PRIMARY KEY(thread_id,user_id)
);
CREATE TABLE hs2_dev.stay_notification_preferences(
 user_id bigint PRIMARY KEY REFERENCES hs2_fixture_legacy.users(id),
 email_enabled boolean NOT NULL DEFAULT false,
 sms_enabled boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE hs2_dev.stay_notifications(
 id uuid PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES hs2_fixture_legacy.users(id),
 source_key text NOT NULL,
 kind text NOT NULL,
 uri text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 read_at timestamptz,
 UNIQUE(user_id,source_key)
);
CREATE TABLE hs2_dev.stay_notification_deliveries(
 id uuid PRIMARY KEY,
 notification_id uuid NOT NULL REFERENCES hs2_dev.stay_notifications(id),
 channel text NOT NULL CHECK(channel IN('email','sms')),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN('pending','failed','sandbox_sent','suppressed')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(notification_id,channel)
);
CREATE INDEX stay_messages_thread_time ON hs2_dev.stay_messages(thread_id,created_at,id);
CREATE INDEX stay_notifications_user_time ON hs2_dev.stay_notifications(user_id,created_at,id);
