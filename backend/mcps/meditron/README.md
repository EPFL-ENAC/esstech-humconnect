# Meditron MCP

_MCP (Model Context Protocol) server for the medical LLM [Meditron](https://github.com/epfllm/meditron)._


## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) Python package and project manager
- Make


## Deploying locally

Setup your environment by running:

```bash
make install
```


### Server

Run:

```bash
make run
```

The MCP server will run at [http://localhost:8000/mcp](http://localhost:8000/mcp).
