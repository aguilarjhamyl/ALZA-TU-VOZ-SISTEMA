#!/usr/bin/env python
"""Start the Django development server."""
import sys

from manage import main


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("runserver")
    main()
