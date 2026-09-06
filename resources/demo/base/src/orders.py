def place_order(user, item):
    return {"user": user, "item": item}

def cancel_order(order_id):
    return {"cancelled": order_id}

def apply_discount(total, percent, code):
    return total

class Cart:
    def add(self, item):
        return item
