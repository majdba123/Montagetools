# HEXA V31 architecture

The engine is organized by responsibility below `extension/py/hexa_v31`. Root-level
modules are compatibility shims only; implementations live in the layer packages.

| Symptom | Owning layer |
| --- | --- |
| Bad crop or white border | extraction |
| Wrong visual object understanding | vision |
| Wrong narrative choice | story |
| Wrong event choice | planning |
| Empty or overlapping composition | layout |
| Bad Arabic text | typography |
| Weak or incorrect movement | motion |
| Plan correct but pixels wrong | render |
| Premiere integration failure | integration |
| False PASS | qa |
| Voice or timing error | audio |

`app` owns CLI/orchestration/pipeline entry points, `core` owns shared low-level
utilities, and `ingest` owns package/media intake. Resource lookups remain anchored
to the extension root, not the moved module directory. The vision subprocess is now
launched as `hexa_v31.vision.vision_worker`; the historical
`python -m hexa_v31.vision_worker` entry point remains a delegating shim.
