import argparse

from content_lab_orchestrator.flows import example_flow


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_cmd = sub.add_parser("list")
    list_cmd.set_defaults(func=lambda _args: print("example_flow"))

    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--name", default="world")
    run_cmd.set_defaults(func=lambda args: print(example_flow(name=args.name)))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
