"""Command line interface: the ``februus`` command.

Each subcommand stores its handler in ``func``; handlers return the exit
code.
"""

import argparse
import logging
import os
import signal
import sys
import threading
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from februus import __version__
from februus.core import keylog
from februus.core.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from februus.core.devices import ImageDevice
from februus.core.session import run_inspectors, run_session
from februus.core.status import Status
from februus.readers.directory import DirectoryReader
from februus.core.verdict import Color, color_of, compute_verdict

# Exit codes of "februus scan".
EXIT_CODES = {Color.GREEN: 0, Color.ORANGE: 1, Color.RED: 2}
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser of the ``februus`` command."""
    parser = argparse.ArgumentParser(
        prog="februus",
        description="Februus USB sheep-dip station.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    commands = parser.add_subparsers(title="commands", metavar="COMMAND")

    config = commands.add_parser("config", help="configuration tools")
    config_commands = config.add_subparsers(title="commands", metavar="COMMAND")
    check = config_commands.add_parser(
        "check",
        help="validate the configuration (main file and conf.d overrides)",
    )
    _add_config_option(check)
    check.set_defaults(func=config_check)
    config.set_defaults(func=lambda args: _print_help(config))

    scan = commands.add_parser(
        "scan",
        help="analyze a folder (development: use config/februus.dev.toml)",
        description="Analyze a folder with the configured reader and analyzers."
        " Exit code: 0 green, 1 orange, 2 red.",
    )
    scan.add_argument("source", help="folder to analyze")
    _add_config_option(scan)
    scan.set_defaults(func=scan_command)

    inspect = commands.add_parser(
        "inspect",
        help="run the inspectors on a disk image file (development)",
        description="Run the configured inspectors on a disk image (an ISO,"
        " a copy of a key made with dd...). Exit code: 0 green, 1 orange, 2 red.",
    )
    inspect.add_argument("image", type=Path, help="disk image file")
    _add_config_option(inspect)
    inspect.set_defaults(func=inspect_command)

    stats = commands.add_parser("stats", help="local statistics of the station")
    stats.add_argument(
        "--days", type=int, default=None, help="only the last N days (default: all)"
    )
    _add_config_option(stats)
    stats.set_defaults(func=stats_command)

    serve = commands.add_parser(
        "serve",
        help="run the Februus service: USB keys, analysis and kiosk screens",
        description="The station service (started by systemd): follows the USB"
        " keys, analyzes them and shows the screens on the configured address.",
    )
    _add_config_option(serve)
    serve.set_defaults(func=serve_command)

    demo = commands.add_parser(
        "demo",
        help="development: the whole station on a folder, with the screens",
        description="Start the screens, then insert and remove a simulated key"
        " (a folder) by pressing Enter. Use config/februus.dev.toml.",
    )
    demo.add_argument("source", type=Path, help="folder used as the key")
    _add_config_option(demo)
    demo.set_defaults(func=demo_command)

    web = commands.add_parser(
        "web",
        help="development: only the screens (idle, and /preview/<screen>)",
    )
    _add_config_option(web)
    web.set_defaults(func=web_command)

    parser.set_defaults(func=lambda args: _print_help(parser))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``februus`` command and return its exit code."""
    args = build_parser().parse_args(argv)
    return args.func(args)


def config_check(args: argparse.Namespace) -> int:
    """Validate the configuration and report every problem found."""
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _print_config_errors(args.config, exc)
        return 1
    print("Configuration OK. Files read:")
    for source in config.sources:
        print(f"  - {source}")
    print(f"Station name: {config.station.name}")
    print(f"Analyzers: {', '.join(config.analyzers.names)}")
    return 0


def scan_command(args: argparse.Namespace) -> int:
    """Run one session on a folder and print the verdict."""
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _print_config_errors(args.config, exc)
        return EXIT_ERROR
    # Development helper: the station creates this folder at install time.
    config.log.path.parent.mkdir(parents=True, exist_ok=True)
    result = run_session(config, Status(), DirectoryReader(), args.source)

    print(f"Session {result.session_id}: {result.files_total} file(s) analyzed")
    for finding in result.findings:
        if finding.color is Color.GREEN:
            continue
        where = _printable(finding.path or "(session)")
        detail = finding.detail.strip().splitlines()[-1] if finding.detail else ""
        print(f"  {finding.color.upper():6} {finding.code:24} {where}  {_printable(detail)}")
    print(f"Verdict: {result.verdict.upper()}")
    return EXIT_CODES[result.verdict]


def inspect_command(args: argparse.Namespace) -> int:
    """Run the inspectors on an image file and print their findings."""
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _print_config_errors(args.config, exc)
        return EXIT_ERROR
    try:
        device = ImageDevice(args.image)
    except OSError as exc:
        print(f"Cannot open the image: {exc}", file=sys.stderr)
        return EXIT_ERROR
    results = run_inspectors(device)
    rules = config.verdict.rules
    for module, code, detail in results:
        color = color_of(code, rules)
        print(f"  {color.upper():6} {code:24} {module}: {_printable(detail)}")
    verdict = compute_verdict([code for _, code, _ in results], rules)
    print(f"Inspection: {verdict.upper()}")
    return EXIT_CODES[verdict]


def stats_command(args: argparse.Namespace) -> int:
    """Print the counts of sessions by verdict, files and bytes analyzed."""
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _print_config_errors(args.config, exc)
        return 1
    since = None
    if args.days is not None:
        since = (datetime.now(UTC) - timedelta(days=args.days)).isoformat(timespec="seconds")
    try:
        numbers = keylog.statistics(config.log.path, since)
    except OSError as exc:
        print(f"Cannot read the key log {config.log.path}: {exc}", file=sys.stderr)
        return 1
    period = f"last {args.days} day(s)" if args.days is not None else "all time"
    print(f"Station {config.station.name}, {period}:")
    print(f"  Sessions: {numbers['sessions']}")
    print(f"    green:  {numbers['green']}")
    print(f"    orange: {numbers['orange']}")
    print(f"    red:    {numbers['red']} (of which key removed too early: {numbers['removed']})")
    print(f"  Files analyzed: {numbers['files']}")
    print(f"  Data analyzed: {numbers['bytes'] / 1e9:.2f} GB")
    return 0


def serve_command(args: argparse.Namespace) -> int:
    """Run the service until stopped (systemd): the key watcher in a
    thread, the screens in the main thread."""
    # Imported here: only this command needs pyudev, uvicorn and real devices.
    import uvicorn

    from februus.core.devices import KernelDevice
    from februus.readers.kernel_mount import KernelMountReader
    from februus.scanner.service import Scanner
    from februus.scanner.udev import key_events
    from februus.web.app import create_app

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _print_config_errors(args.config, exc)
        return 1
    status = Status()
    reader = KernelMountReader(
        config.scan.mount_timeout_seconds, config.scan.cancel_check_ms / 1000
    )
    scanner = Scanner(config, status, reader, open_device=KernelDevice)
    failed = threading.Event()

    def watch_keys() -> None:
        try:
            for event in key_events(
                config.scanner.settle_seconds, config.scanner.poll_interval_ms / 1000
            ):
                if event is not None:
                    logging.info("key %s: %s %s", event.action, event.disk, event.partitions)
                    scanner.handle(event)
                scanner.tick()
        except Exception:
            logging.exception("the key watcher stopped")
            failed.set()
        # FAIL-CLOSED: without the watcher the station checks nothing. The
        # screens show "out of service" at once, then the service stops and
        # systemd starts it again.
        # FR : sans surveillance des clés la station ne vérifie plus rien :
        # écran « hors service », puis arrêt du service (systemd le relance).
        os.kill(os.getpid(), signal.SIGTERM)

    watcher = threading.Thread(target=watch_keys, name="key-watcher", daemon=True)
    app = create_app(config, status, scanner_alive=watcher.is_alive)
    server = uvicorn.Server(uvicorn.Config(app, host=config.web.host, port=config.web.port))
    # The port is taken BEFORE the keys are watched: a second service (the
    # port is in use) stops here and never analyzes a key.
    # FR : le port est pris AVANT de surveiller les clés : un second service
    # s'arrête ici et n'analyse jamais de clé.
    sock = server.config.bind_socket()
    watcher.start()
    server.run(sockets=[sock])
    return 1 if failed.is_set() else 0


def demo_command(args: argparse.Namespace) -> int:
    """Development: the screens and a simulated key (a folder)."""
    import uvicorn

    from februus.scanner.service import KeyEvent, Scanner
    from februus.web.app import create_app

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _print_config_errors(args.config, exc)
        return 1
    config.log.path.parent.mkdir(parents=True, exist_ok=True)
    status = Status()
    # No device: the inspectors only run on a real key (or "februus inspect").
    scanner = Scanner(config, status, DirectoryReader(), open_device=lambda disk: None)
    server = uvicorn.Server(uvicorn.Config(
        create_app(config, status), host=config.web.host, port=config.web.port,
        log_level="warning",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    print(f"Open http://{config.web.host}:{config.web.port} in a browser (Ctrl-C to stop).")
    try:
        while True:
            input("Press Enter to insert the key... ")
            scanner.handle(KeyEvent("add", "/dev/demo", (str(args.source),)))
            scanner.wait()
            input("Press Enter to remove the key... ")
            scanner.handle(KeyEvent("remove", "/dev/demo"))
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
    return 0


def web_command(args: argparse.Namespace) -> int:
    """Development: only the screens (idle, and the previews)."""
    import uvicorn

    from februus.web.app import create_app

    try:
        config = load_config(args.config)
        app = create_app(config, Status())
    except ConfigError as exc:
        _print_config_errors(args.config, exc)
        return 1
    uvicorn.run(app, host=config.web.host, port=config.web.port)
    return 0


def _print_config_errors(path: Path, exc: ConfigError) -> None:
    print(f"Configuration INVALID ({path}):", file=sys.stderr)
    for error in exc.errors:
        print(f"  - {error}", file=sys.stderr)


def _printable(text: str) -> str:
    """Escape control characters: names come from the key (untrusted) and
    could hold terminal escape sequences.
    FR : les noms viennent de la clé ; on neutralise les caractères de
    contrôle du terminal."""
    return "".join(c if c.isprintable() else repr(c)[1:-1] for c in text)


def _add_config_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"configuration file (default: {DEFAULT_CONFIG_PATH})",
    )


def _print_help(parser: argparse.ArgumentParser) -> int:
    parser.print_help()
    return 0
