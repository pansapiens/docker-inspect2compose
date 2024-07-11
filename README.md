# docker-inspect2compose

`docker-inspect2compose` is a simple Python program that converts Docker container information into a 
Docker Compose service definition. It retrieves information about running containers on the host
and generates a `docker-compose.yml` configuration. The script can also merge this information 
into an existing `docker-compose.yml` file.

_Why would you want this ?_ Maybe you started a container using `docker run`. Maybe you started it so
long ago, you don't quite remember the volume mounts and other options you used. This allows you
to capture some key information to create a more permanent Docker Compose definition.

## Features

- Retrieves Docker container information using Docker SDK or `docker inspect` command.
- Generates Docker Compose service (`docker-compose.yml`) definition.
- Includes `deploy.restart_policy`, `deploy.resources`, `logging`, and `networks` sections if available.
- Include environment variable (optionally including `PATH`)
- `--add-to` merges a new service definition into an existing `docker-compose.yml` file.

> The output may not capture every possible Docker Compose configuration option, but captures the 
> main settings used in simple deployments. Sections like `build:` won't be added 
> since `docker inspect` doesn't have this information.

## Requirements

- Python 3.6+
- Docker SDK for Python (`docker-py`)
- PyYAML

## Installation

1. Clone the repository:
   ```sh
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Install the package:
   ```sh
   pip install .
   ```

## Usage

First, find a running container id or name using `docker ps`.

```sh
docker-inspect2compose [container_id_or_name] [options]
```

### Options

- `--output`, `-o`: Output file to write the Docker Compose definition. Use `-` for stdout. Default is `-`.
- `--include-path-env`: Include the `PATH` environment variable in the output.
- `--add-to`: Path to an existing `docker-compose.yml` file to add the new service to.

### Examples

- Print the Docker Compose definition for all running containers to stdout:
  ```sh
  docker-inspect2compose
  ```

- Write the Docker Compose definition to a file for a single container:
  ```sh
  docker-inspect2compose [container_id_or_name] --output <output_file>
  ```

- Include the `PATH` environment variable in the output:
  ```sh
  docker-inspect2compose --include-path-env
  ```

- Add a new service to an existing `docker-compose.yml` file:
  ```sh
  docker-inspect2compose [container_id_or_name] --add-to <path_to_existing_docker_compose_yml> --output <output_file>
  ```

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## See also

- [kurron/docker-inspect-to-compose](https://github.com/kurron/docker-inspect-to-compose) - a Java implementation of a similar idea that worked for me, but outputs a more complex (complete?) service definition.
