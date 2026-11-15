# AirCursor macOS Backend

The native macOS input adapter uses CoreGraphics through PyObjC. It provides pointer movement, relative movement, left/right/middle click and drag, scroll, and cursor-position queries.

## Install

From the repository root on macOS:

```bash
python -m pip install -e ".[macos]"
```

## Permissions

macOS requires explicit permission before an application can synthesize input. Add the terminal, Python launcher, or packaged AirCursor application under **System Settings → Privacy & Security → Accessibility**. Depending on the macOS release and deployment setup, Input Monitoring permission may also be required.

## Example

```python
from macos import MacOSEventSynthesizer

mouse = MacOSEventSynthesizer()
x, y = mouse.current_location()
mouse.move_to(x + 40, y + 20)
mouse.click("left")
mouse.scroll(vertical=3)
```

All coordinates use global macOS display points. CoreGraphics event posting is local; this adapter does not communicate with a cloud service. Use it only in a user-authorized desktop session. Headless CI tests inject a fake Quartz API and do not emit real system input.
