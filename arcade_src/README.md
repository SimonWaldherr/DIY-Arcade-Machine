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

Every registered game inherits `FrameLoopGame` and implements
`_build_step(joystick)`, returning one nonblocking callback (`True` to continue,
`False` to finish). Set `FRAME_MS` to the gameplay interval; do not add separate
desktop, browser or hardware loops. Initialize/reset the run in `_build_step`.

`GameSession` owns the shared pause menu, input filtering, frame restoration and
pause-aware game clock. Use `ticks_ms`/`ticks_add` for gameplay deadlines;
`raw_ticks_ms` is reserved for input, the menu and frame pacing. For sequential
animations, `_timed_game_step` adapts a generator yielding delays in milliseconds.
Do not block a game callback with sleeps or input-release loops.

C+Z always opens pause. C alone does too, unless `SECONDARY_ACTION = True` or
`uses_secondary_action()` declares a contextual secondary action. CPU demo
controllers retain their synthetic C exit. Demos call game callbacks directly,
so the outer session can still pause the whole preview.

The selector handles `RESTART` and `EXIT` session results centrally, recreating
the game from its selected settings on restart and keeping pause exits out of
the high-score/game-over flow. Gameplay should report actual wins/losses with
`set_game_over_score`.
