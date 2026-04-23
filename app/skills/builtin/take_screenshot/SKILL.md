# take_screenshot

Capture the screen and return a local image path. Wraps the bound `screen-capture` MCP.

## Prerequisites

Agent must have the `screen-capture` MCP bound (not optional).

## Canonical call

```python
skill(take_screenshot, {})          # full screen (default)
skill(take_screenshot, {"region": "full"})
skill(take_screenshot, {"region": "window"})     # frontmost window
skill(take_screenshot, {"region": "selection"})  # user-drawn rectangle
```

## Returns

```python
{
    "image_path": "/abs/path/to/screenshot.png",
    "width":      2560,
    "height":     1440
}
```

The returned path is an absolute file on disk — you can pass it to `read_file`, attach it to an email, or inspect the image directly.

## Field notes

- **region**: one of `full` / `window` / `selection`. Default is `full`.
  - `window` captures whichever app is frontmost when the skill fires.
  - `selection` opens an interactive selector — the user draws a rectangle. Blocks until they finish.

## Failure modes

| Symptom | Fix |
|---|---|
| `No screen-capture MCP bound` | Bind it in the admin UI |
| Permission denied (macOS) | User needs to grant Screen Recording permission in System Settings → Privacy & Security |
| Empty / black image | Usually display sleep; ask the user to wake the screen and retry |
