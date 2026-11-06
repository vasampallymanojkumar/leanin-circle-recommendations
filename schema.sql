PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS topics (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, label TEXT NOT NULL, domain TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, has_photo INTEGER NOT NULL,
 bio TEXT, job_title TEXT, company TEXT, industry TEXT, location TEXT,
 joined_at TEXT NOT NULL, profile_completeness REAL CHECK(profile_completeness BETWEEN 0 AND 1));
CREATE TABLE IF NOT EXISTS user_interests (
 user_id INTEGER REFERENCES users(id), topic_slug TEXT REFERENCES topics(slug), PRIMARY KEY(user_id,topic_slug));
CREATE TABLE IF NOT EXISTS circles (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL, description TEXT,
 topic TEXT REFERENCES topics(slug), cover_image_url TEXT,
 format TEXT CHECK(format IN ('virtual','in_person','hybrid')),
 access TEXT CHECK(access IN ('public','unlisted')), join_policy TEXT CHECK(join_policy IN ('open','request')),
 max_members INTEGER CHECK(max_members IS NULL OR max_members >= 0), member_count INTEGER CHECK(member_count>=0),
 created_at TEXT, last_activity_at TEXT, feed_posts_30d INTEGER, chat_messages_30d INTEGER);
CREATE TABLE IF NOT EXISTS circle_tags (
 circle_id INTEGER REFERENCES circles(id), tag TEXT NOT NULL, PRIMARY KEY(circle_id,tag));
CREATE TABLE IF NOT EXISTS memberships (
 user_id INTEGER REFERENCES users(id), circle_id INTEGER REFERENCES circles(id),
 role TEXT CHECK(role IN ('member','leader')), joined_at TEXT, PRIMARY KEY(user_id,circle_id));
CREATE INDEX IF NOT EXISTS memberships_by_circle ON memberships(circle_id,user_id);
CREATE INDEX IF NOT EXISTS interests_by_topic ON user_interests(topic_slug,user_id);
CREATE INDEX IF NOT EXISTS circles_by_discovery ON circles(access,last_activity_at);
CREATE INDEX IF NOT EXISTS circles_by_topic ON circles(topic);
CREATE TABLE IF NOT EXISTS activity (
 id INTEGER PRIMARY KEY, circle_id INTEGER REFERENCES circles(id), author_user_id INTEGER REFERENCES users(id),
 body TEXT, reaction_count INTEGER, comment_count INTEGER, save_count INTEGER, created_at TEXT,
 FOREIGN KEY(author_user_id,circle_id) REFERENCES memberships(user_id,circle_id));
CREATE INDEX IF NOT EXISTS activity_by_circle_date ON activity(circle_id,created_at);
