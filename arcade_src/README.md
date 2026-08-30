# Modular arcade source

`arcade_app.py` is a generated, single-file bundle for MicroPython, desktop,
and pygbag. Edit the ordered fragments in this directory instead of editing
the bundle directly, then run:

```sh
make arcade-bundle
```

The fragments deliberately share one global namespace. They are concatenated
rather than imported at runtime so the RP2040 build keeps the low memory and
startup characteristics of the original application.

`make check` verifies that the committed bundle is current and runs the test
suite. Fragment order is defined in `tools/build_arcade_bundle.py`.
