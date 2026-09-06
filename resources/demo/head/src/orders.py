def place_order(user, item, qty):
    return {"user": user, "item": item, "qty": qty}

def void_order(order_id):
    return {"cancelled": order_id}

def apply_discount(total, percent):
    return total

class Cart:
    def add(self, item, quantity):
        return (item, quantity)
