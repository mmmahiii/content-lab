from __future__ import annotations

import argparse
from collections.abc import Sequence

from content_lab_orchestrator.flows import (
    DEFAULT_FLOW_NAME,
    get_flow_definition,
    list_flow_names,
    run_flow,
)


def _list_flows(_args: argparse.Namespace) -> None:
    for flow_name in list_flow_names():
        print(flow_name)


def _run_selected_flow(args: argparse.Namespace) -> None:
    flow_definition = get_flow_definition(args.flow)
    flow_kwargs = flow_definition.build_kwargs(args)
    print(run_flow(flow_definition.name, **flow_kwargs))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_cmd = sub.add_parser("list")
    list_cmd.set_defaults(func=_list_flows)

    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--flow", default=DEFAULT_FLOW_NAME, choices=list_flow_names())
    run_cmd.add_argument("--name", default="world")
    run_cmd.add_argument("--reel-id", default="demo-reel")
    run_cmd.add_argument("--dry-run", action="store_true")
    run_cmd.set_defaults(func=_run_selected_flow)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
