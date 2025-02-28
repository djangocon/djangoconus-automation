# DjangoCon US Automation

Django Project to automate tasks for the DjangoCon US.

## Getting started

### Using Docker

To run this project locally, we recommend installing [Docker Compose](https://docs.docker.com/compose/install/).

### First steps

The project expects a few variables to be set in our `.env` file. To get started, copy the `.env-dist` file to `.env` so that Docker Compose may read it.

```shell
cp .env-dist .env
```

Now edit `.env` in your favorite text editor if you want to test against our Sendy email service or Slack.

### Build the docker image:

```shell
docker compose build
```

### Run the container:

```shell
docker compose up
```

You should be able to access the server on [http://localhost:8000](http://localhost:8000).

## Deploying

### Deploying to our dev server

To install the `flyctl` command-line utility, check out the [Install flyctl](https://fly.io/docs/hands-on/install-flyctl/) on Fly.io's website.

To deploy to the dev server:

```shell
flyctl deploy

# open our dev server
open https://dcus-automation.fly.dev
```

### Deploying to our production server

To deploy to the production server:

```shell
flyctl deploy --config fly.production.toml

# open our production server
open https://dcus-automation-prod.fly.dev
```
You can add a section explaining the automatic deployment process when branches are merged to the main branch. Here's an updated version of the README:

```markdown
# DjangoCon US Automation

Django Project to automate tasks for the DjangoCon US.

## Getting started

### Using Docker

To run this project locally, we recommend installing [Docker Compose](https://docs.docker.com/compose/install/).

### First steps

The project expects a few variables to be set in our `.env` file. To get started, copy the `.env-dist` file to `.env` so that Docker Compose may read it.

```shell
cp .env-dist .env
```

Now edit `.env` in your favorite text editor if you want to test against our Sendy email service or Slack.

### Build the docker image:

```shell
docker compose build
```

### Run the container:

```shell
docker compose up
```

You should be able to access the server on [http://localhost:8000](http://localhost:8000).

## Deploying

### Deploying to our dev server

To install the `flyctl` command-line utility, check out the [Install flyctl](https://fly.io/docs/hands-on/install-flyctl/) on Fly.io's website.

To deploy to the dev server:

```shell
flyctl deploy

# open our dev server
open https://dcus-automation.fly.dev
```

You can add a section explaining the automatic deployment process when branches are merged to the main branch. Here's an updated version of the README:

```markdown
# DjangoCon US Automation

Django Project to automate tasks for the DjangoCon US.

## Getting started

### Using Docker

To run this project locally, we recommend installing [Docker Compose](https://docs.docker.com/compose/install/).

### First steps

The project expects a few variables to be set in our `.env` file. To get started, copy the `.env-dist` file to `.env` so that Docker Compose may read it.

```shell
cp .env-dist .env
```

Now edit `.env` in your favorite text editor if you want to test against our Sendy email service or Slack.

### Build the docker image:

```shell
docker compose build
```

### Run the container:

```shell
docker compose up
```

You should be able to access the server on [http://localhost:8000](http://localhost:8000).

## Deploying

### Deploying to our dev server

To install the `flyctl` command-line utility, check out the [Install flyctl](https://fly.io/docs/hands-on/install-flyctl/) on Fly.io's website.

To deploy to the dev server:

```shell
flyctl deploy

# open our dev server
open https://dcus-automation.fly.dev
```

### Deploying to our production server

To deploy to the production server:

```shell
flyctl deploy --config fly.production.toml

# open our production server
open https://dcus-automation-prod.fly.dev
```

### Automatic Deployments

Deployments happen automatically when branches are merged to the `main` branch on GitHub. This ensures that the latest changes are always deployed without manual intervention.

### Deploying to our production server Manually

To deploy to the production server:

```shell
flyctl deploy --config fly.production.toml

# open our production server
open https://dcus-automation-prod.fly.dev
```
