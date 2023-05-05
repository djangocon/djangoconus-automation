# DjangoCon US Automation

Django Project to automate tasks for the DjangoCon.

## Getting started

### Using Docker

- Build the docker image:

```shell
docker build -t djus-automation .
```

- Run the container:

```shell
docker run -p 8000:8000 djus-automation
```

You should be able to access the server on [http://localhost:8000](http://localhost:8000).

## Deploying

To deploy to the dev server:

```shell
flyctl deploy
```

To deploy to the production server:

```shell
flyctl deploy --config fly.production.toml
```
