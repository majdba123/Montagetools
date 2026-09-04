"""Motion layer and lazy compatibility exports for ``hexa_v31.motion``."""

def __getattr__(name):
    if name == 'build_motion_plan':
        from hexa_v31.interaction.director import build_interaction_motion_plan
        value = build_interaction_motion_plan
    else:
        from importlib import import_module
        implementation = import_module(__name__ + '.motion')
        value = getattr(implementation, name)
    globals()[name] = value
    return value
