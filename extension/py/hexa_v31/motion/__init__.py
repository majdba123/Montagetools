"""Motion layer and lazy compatibility exports for ``hexa_v31.motion``."""

def __getattr__(name):
    # Do not eagerly import motion.py: legacy imports of hexa_v31.motion_solver
    # need this package to initialize without re-entering motion.py.
    from importlib import import_module
    implementation = import_module(__name__ + '.motion')
    value = getattr(implementation, name)
    globals()[name] = value
    return value
