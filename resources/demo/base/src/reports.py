from .archive import archive_order
def monthly(orders):
    return [archive_order(o) for o in orders]
