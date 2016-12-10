CREATE TABLE feeds (
    id SERIAL PRIMARY KEY,
    full_name varchar(64),
    short_name varchar(32),
    favicon text,
    color char(6),
    module text,
    config jsonb,
    is_public boolean,
    is_updating boolean,
    is_searchable boolean
);

CREATE TABLE events (
    id uuid PRIMARY KEY,
    feed_id int references feeds(id),
    title text,
    text text,
    link text,
    occurred timestamptz NOT NULL,
    raw json,
    thumbnail jsonb,
    original jsonb,
    archived jsonb,
    is_related boolean
);

CREATE INDEX events_occurred ON events(occurred DESC);
CREATE INDEX events_occurred_and_id ON events(occurred DESC, id DESC);
CREATE INDEX events_is_related ON events(is_related);
CREATE INDEX events_feed_id_and_occurred ON events(feed_id, occurred DESC);
CREATE INDEX events_title ON events(title);
CREATE INDEX events_link ON events(link);

CREATE TABLE related_events (
    parent uuid references events(id),
    child uuid references events(id),
    PRIMARY KEY(parent, child)
);

CREATE INDEX related_events_by_parent ON related_events(parent);