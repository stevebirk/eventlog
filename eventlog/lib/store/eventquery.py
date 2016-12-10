from .query import Query


class EventQuery:
    def __init__(self, basequery, embed_feeds=True, embed_related=True):

        template = "with e as ({basequery})"

        template += """
            select row_to_json(row) from (
                select e.id, e.title, e.text, e.link, e.occurred,
                       e.raw, e.thumbnail, e.original, e.archived"""

        if embed_feeds:
            template += ", fd as feed"

        if embed_related:
            template += ", p.children as related"

        template += " from e"

        if embed_feeds:
            template += """
            inner join (
                select f.id, f.full_name, f.short_name, f.favicon, f.color
                from feeds f
            ) fd(id, full_name, short_name, favicon, color)
            on fd.id = e.feed_id
            """

        if embed_related:
            template += """
            left outer join (
                select e.id,
                       array_to_json(
                           array_agg(cd.* order by cd.occurred asc)
                       ) as children
                from e
                inner join related_events re on re.parent = e.id
                left outer join (
                    select c.id, c.title, c.text, c.link, c.occurred,
                           c.raw, c.thumbnail, c.original, c.archived
                    from events c
                ) cd(id, title, text, link, occurred,
                     raw, thumbnail, original, archived) on cd.id = re.child
                group by e.id
            ) p on e.id = p.id
            """

        template += " {sort}) row;"

        self.template = template

        self.basequery = basequery

        self.aliases = {'events': 'e'}

        self.sort = 'order by {events}.occurred desc, {events}.id desc'
        self.limit = None
        self.cursor = None

    def set_limit(self, limit):
        self.limit = limit

    def set_cursor(self, cursor):
        self.cursor = cursor

    def add_clause(self, clause, params=None):
        self.basequery = self.basequery.add_clause(clause, params=params)

    @property
    def query(self):
        query = self.basequery

        if self.cursor is not None:
            query = query.add_clause(
                "({events}.occurred, {events}.id) < (%s, %s)"
            )

        query += ' ' + self.sort

        if self.limit is not None:
            query += ' limit %s'

        query = Query(
            self.template.format(basequery=query, sort=self.sort),
            params=query.params,
            aliases=self.aliases
        )

        return query.format()

    @property
    def params(self):
        params = self.basequery.params

        if self.cursor is not None:
            params += (self.cursor.occurred, self.cursor.id)

        if self.limit is not None:
            params += (self.limit,)

        return params
