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
from content_lab_orchestrator.prefect_compat import extend_prefect_ephemeral_lifespan_timeout


def _list_flows(_args: argparse.Namespace) -> None:
    for flow_name in list_flow_names():
        print(flow_name)


def _run_selected_flow(args: argparse.Namespace) -> None:
    flow_definition = get_flow_definition(args.flow)
    flow_kwargs = flow_definition.build_kwargs(args)
    try:
        print(run_flow(flow_definition.name, **flow_kwargs))
    except BaseException as exc:
        # The API launches this CLI as a detached process and only learns the outcome from
        # the run row. Without this, a crash before the flow starts left the run "queued"
        # forever.
        if args.run_id:
            _mark_run_failed(args.run_id, error=f"{type(exc).__name__}: {exc}")
        raise


def _mark_run_failed(run_id: str, *, error: str) -> None:
    """Best-effort: mark a still-open run as failed. Never masks the original error."""

    try:
        from sqlalchemy import create_engine, text

        from content_lab_shared.settings import Settings

        engine = create_engine(Settings().database_url, pool_pre_ping=True)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE runs SET status = 'failed', finished_at = now(), "
                        "output_payload = COALESCE(output_payload, '{}'::jsonb) "
                        "|| jsonb_build_object('error', CAST(:error AS text), "
                        "'phase', 'orchestrator_process') "
                        "WHERE id = CAST(:run_id AS uuid) "
                        "AND status IN ('pending', 'queued', 'running')"
                    ),
                    {"run_id": run_id, "error": error[:2000]},
                )
        finally:
            engine.dispose()
    except Exception as mark_exc:  # pragma: no cover - logging only
        print(f"could not mark run {run_id} failed: {mark_exc}")


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
    extend_prefect_ephemeral_lifespan_timeout()
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
