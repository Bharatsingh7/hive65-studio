"""AppImage entry: `Hive65.AppImage` opens Studio; `Hive65.AppImage scene Party` (any
hive65 subcommand) runs the command line instead."""
import sys

if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    from hive65.cli import main
    sys.exit(main(sys.argv[1:]))
else:
    from hive65.studio.app import main
    main()
