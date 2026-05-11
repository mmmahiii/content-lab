from __future__ import annotations

import argparse
from collections.abc import Sequence

from content_lab_orchestrator.flows import (
    DEFAULT_FLOW_NAME,
    get_flow_definition,
    list_flow_names,
    run_flow,
)
from content_lab_orchestrator.flows.daily_reel_factory import DEFAULT_FACTORY_DISPATCH_MODE


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
    run_cmd.add_argument(
        "--factory-dispatch-mode",
        default=DEFAULT_FACTORY_DISPATCH_MODE,
        choices=("production", "smoke"),
        help=(
            "For daily_reel_factory only: production invokes process_reel per reel; "
            "smoke records explicit no-ops (default). Other flows ignore this flag."
        ),
    )
    run_cmd.add_argument("--reel-id", default="demo-reel")
    run_cmd.add_argument("--run-id", default=None)
    run_cmd.add_argument("--dry-run", action="store_true")
    run_cmd.add_argument("--org-id", default="")
    run_cmd.add_argument("--asset-pack-id", default=None)
    run_cmd.add_argument("--asset-pack-name", default=None)
    run_cmd.add_argument("--niche", default="")
    run_cmd.add_argument("--requested-asset-count", type=int, default=1)
    run_cmd.add_argument("--auto-approve", action="store_true")
    run_cmd.add_argument("--target-reel-count", type=int, default=5)
    run_cmd.add_argument("--render-selected", action="store_true")
    run_cmd.add_argument("--render-limit", type=int, default=1)
    run_cmd.add_argument("--page-id", default=None)
    run_cmd.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="For outbox_drain only: number of outbox events to process per batch. Other flows ignore this flag.",
    )
    run_cmd.set_defaults(func=_run_selected_flow)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
