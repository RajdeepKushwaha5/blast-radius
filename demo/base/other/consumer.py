# imports the OTHER place_order - must not be flagged
from other.legacy import place_order
def go():
    return place_order(1, 2)
