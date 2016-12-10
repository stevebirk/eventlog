class Query:

    def __init__(self, query, params=None, aliases=None):
        self.query = query
        self.params = params
        self.aliases = aliases

        if params is None:
            self.params = ()

        if aliases is None:
            self.aliases = {
                'events': 'e',
                'feeds': 'f'
            }

        self.clause_modifier = (
            'where' if 'where' not in self.query.lower() else 'and'
        )

    def add_clause(self, clause, params=None):
        new_query = (
            self.query + ' ' + self.clause_modifier + ' ' + clause
        )

        new_params = self.params

        if params is not None:
            new_params += params

        return Query(new_query, params=new_params, aliases=self.aliases)

    def format(self):
        return self.query.format(**self.aliases)

    def __iadd__(self, other):
        return Query(
            self.query + other,
            params=self.params,
            aliases=self.aliases
        )

    def __format__(self, format_spec):
        return self.format()
