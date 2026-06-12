# HumConnect

_Humanitarian Connector for the EssentialTech Centre's HUD program_


## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) Python package and project manager
- [npm](https://docs.npmjs.com/) Node.js package manager
- Make


## Deploying locally


Clone the repository with submodules:

```bash
git clone
cd esstech-humconnect
git submodule update --init
```

Setup your environment by running:

```bash
make install
```


### Backend

In one shell, run:

```bash
make run-db
make run-backend
```

The interactive API documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

### Frontend

In another shell, run:

```bash
make run-frontend
```

The website will be available at [http://localhost:9000](http://localhost:9000).
