class Page(object):
    def __init__(self, events, next_page, prev_page, total_count):
        self.next = next_page
        self.prev = prev_page
        self.events = events
        self.total_count = total_count
