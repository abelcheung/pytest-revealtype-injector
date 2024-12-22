pytest_plugins = ["pytester"]

# Tests in this folder are fragile. If return type is taken away from function
# (the "-> None" part), mypy will not complain about the type hint under
# non-strict mode. Instead, it infers a blanket type of "Any" for "x", which
# nullifies typeguard checking (no TypeCheckError raised). A crude guard against
# this situation is implemented inside revealtype_injector.
