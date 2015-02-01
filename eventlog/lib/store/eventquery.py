class EventQuery(object):
    def __init__(self, basequery, baseparams=None, embed_feeds=True,
                 embed_related=True):
        template = """with e as (%s)
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

        template += " order by occurred desc"
        template += ") row;"

        self.template = template
        self.basequery = basequery
        self.baseparams = ()
        if baseparams is not None:
            self.baseparams = baseparams

        self.sort = None
        self.limit = None
        self.offset = None

    def add_clause(self, clause, params):
        if 'where' not in self.basequery.lower():
            self.basequery += ' where '
        else:
            self.basequery += ' and '

        self.basequery += clause
        self.baseparams += params

    def add_sort(self, field, direction='desc'):
        self.sort = 'order by %s %s' % (
            field,
            direction
        )

    def add_limit(self, limit, offset=None):
        self.limit = limit
        self.offset = offset

    @property
    def query(self):
        basequery = self.basequery

        if self.sort is not None:
            basequery += ' ' + self.sort

        if self.limit is not None:
            basequery += ' limit %s'

        if self.offset is not None:
            basequery += ' offset %s'

        return self.template % basequery

    @property
    def params(self):
        params = self.baseparams

        if self.limit is not None:
            params += (self.limit,)

        if self.offset is not None:
            params += (self.offset,)

        return params
