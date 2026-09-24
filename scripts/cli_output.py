"""UTF-8 output for executable entry points, without import-time stream changes."""
import sys


def configure_utf8_output():
    # A CLI's pipes must have a deterministic encoding regardless of the host
    # code page. Embedded callers and StringIO retain their own stream policy.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            reconfigure(encoding='utf-8', errors='backslashreplace')
