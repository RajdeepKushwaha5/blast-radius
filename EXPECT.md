| file | symbol | expected |
|---|---|---|
| src/worker.py | place_order | ORPHANED_CALL_SITE (passes 2, requires 3) |
| src/admin.py | cancel_order | REMOVED_SYMBOL_STILL_CALLED |
| src/billing.py | apply_discount | ORPHANED_CALL_SITE (passes 3, max 2) |
| src/carts.py | Cart.add | ORPHANED_CALL_SITE (passes 1, requires 2) |
| src/dynamic.py | place_order | INDETERMINATE (argument unpacking) |
| src/api.py | - | none, the refactor updated it |
| other/consumer.py | - | none, a different place_order |
