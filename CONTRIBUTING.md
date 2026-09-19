# Contributing

## Development setup

Install [uv](https://docs.astral.sh/uv/), then run:

```shell
uv sync --frozen
uv run edu-roi --help
uv run pytest
```

Before opening a pull request:

```shell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

Use `uv run ruff format .` to format changes. Keep domain logic independent from the CLI and add tests for behavior. Do not commit downloaded source datasets, credentials, local databases, or generated results.

## Containers

Docker is optional. Build and run the CLI help with `docker build -t education-roi .` and `docker run --rm education-roi`.

`docker compose run --rm edu-roi paths` mounts local `data/` and `results/` directories under `/workspace`.

## License

Contributions are accepted under the repository's MIT License.

