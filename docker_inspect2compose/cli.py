#!/usr/bin/env python

import argparse
import logging
import os
import sys
from typing import Dict, Any, List, Optional
from collections import OrderedDict

try:
    import docker
    from docker.errors import NotFound, APIError, DockerException

    DOCKER_SDK_AVAILABLE = True
except ImportError:
    DOCKER_SDK_AVAILABLE = False

import yaml
import subprocess
import json

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)


def run_command(command: str) -> str:
    result = subprocess.run(
        command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return result.stdout.decode("utf-8")


def docker_inspect(container_id: str) -> Dict[str, Any]:
    command = f"docker inspect {container_id}"
    output = run_command(command)
    return json.loads(output)[0]


def get_container_info(container_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if DOCKER_SDK_AVAILABLE:
        try:
            client = docker.from_env()
            if container_id:
                containers = [client.containers.get(container_id)]
            else:
                containers = client.containers.list()
            return [container.attrs for container in containers]
        except DockerException as e:
            logging.error(f"Docker exception occurred: {e}")
            sys.exit(1)
    else:
        if container_id:
            return [docker_inspect(container_id)]
        else:
            output = run_command("docker ps -q")
            container_ids = output.split()
            return [docker_inspect(cid) for cid in container_ids]


def transform_to_compose(
    service_name: str, inspect_data: Dict[str, Any], include_path_env: bool
) -> OrderedDict:
    def get_ports() -> List[str]:
        ports = inspect_data["NetworkSettings"]["Ports"]
        return [
            f"{host_port['HostPort']}:{container_port.split('/')[0]}"
            for container_port, host_ports in ports.items()
            if host_ports is not None
            for host_port in host_ports
        ]

    def get_volumes() -> List[str]:
        return [
            f"{mount['Source']}:{mount['Destination']}"
            for mount in inspect_data["Mounts"]
        ]

    def get_environment() -> List[str]:
        env = inspect_data["Config"]["Env"]
        if not include_path_env:
            env = [e for e in env if not e.startswith("PATH=")]
        return env

    def get_restart_policy() -> Dict[str, Any]:
        restart_policy = inspect_data["HostConfig"]["RestartPolicy"]
        if restart_policy["Name"]:
            policy = {"condition": restart_policy["Name"]}
            if restart_policy["Name"] == "on-failure":
                policy["max_attempts"] = restart_policy.get("MaximumRetryCount", 0)
            return policy
        return {}

    def get_resources() -> Dict[str, Any]:
        resources = {}
        if inspect_data["HostConfig"]["NanoCpus"]:
            resources["cpus"] = str(inspect_data["HostConfig"]["NanoCpus"] / 1e9)
        if inspect_data["HostConfig"]["Memory"]:
            resources["memory"] = inspect_data["HostConfig"]["Memory"]
        return resources

    def get_logging() -> Dict[str, Any]:
        log_config = inspect_data["HostConfig"]["LogConfig"]
        if log_config["Type"]:
            return {"driver": log_config["Type"], "options": log_config["Config"]}
        return {}

    def get_networks() -> List[str]:
        return list(inspect_data["NetworkSettings"]["Networks"].keys())

    environment = get_environment()
    restart_policy = get_restart_policy()
    resources = get_resources()
    logging_config = get_logging()
    networks = get_networks()

    service_dict = OrderedDict(
        {
            "image": inspect_data["Config"]["Image"],
            "container_name": service_name,
            "ports": get_ports(),
            "volumes": get_volumes(),
        }
    )

    if environment:
        service_dict["environment"] = environment
    if restart_policy:
        service_dict["deploy"] = {"restart_policy": restart_policy}
    if resources:
        if "deploy" not in service_dict:
            service_dict["deploy"] = {}
        service_dict["deploy"]["resources"] = resources
    if logging_config:
        service_dict["logging"] = logging_config
    if networks:
        service_dict["networks"] = networks

    config = OrderedDict({"version": "3.8", "services": {service_name: service_dict}})

    return config


def write_compose(compose_data: Dict[str, Any], output: str) -> None:
    # Convert OrderedDict to regular dict for YAML dumping
    compose_data = json.loads(json.dumps(compose_data))
    with open(output, "w") if output != "-" else sys.stdout as f:
        yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)


def load_existing_compose(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def merge_compose(
    existing_compose: Dict[str, Any], new_services: List[Dict[str, Any]]
) -> Dict[str, Any]:
    if "services" not in existing_compose:
        existing_compose["services"] = {}
    for new_service in new_services:
        service_name = list(new_service["services"].keys())[0]
        if service_name not in existing_compose["services"]:
            existing_compose["services"].update(new_service["services"])
    return existing_compose


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transform Docker container info to Docker Compose service definition."
    )
    parser.add_argument(
        "container",
        nargs="?",
        default=None,
        help="ID or name of the running Docker container (optional)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file to write the Docker Compose definition. Use '-' for stdout.",
        default="-",
    )
    parser.add_argument(
        "--include-path-env",
        action="store_true",
        help="Include the PATH environment variable in the output",
    )
    parser.add_argument(
        "--add-to",
        help="Path to an existing docker-compose.yml file to add the new service to.",
    )
    args = parser.parse_args()

    try:
        containers_info = get_container_info(args.container)
        new_services = [
            transform_to_compose(
                inspect_data["Name"].strip("/"), inspect_data, args.include_path_env
            )
            for inspect_data in containers_info
        ]

        if args.add_to:
            existing_compose = load_existing_compose(args.add_to)
            updated_compose = merge_compose(existing_compose, new_services)
            write_compose(updated_compose, args.output)
        else:
            combined_services = OrderedDict({"version": "3.8", "services": {}})
            for service in new_services:
                combined_services["services"].update(service["services"])
            write_compose(combined_services, args.output)

        logging.info("Docker Compose service definition(s) created successfully.")
    except NotFound:
        logging.error(f"Container {args.container} not found.")
        sys.exit(1)
    except APIError as e:
        logging.error(f"Docker API error: {e}")
        sys.exit(1)
    except DockerException as e:
        logging.error(f"Docker exception occurred: {e}")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing command: {e}")
        sys.exit(1)
    except json.JSONDecodeError:
        logging.error("Error decoding JSON from docker inspect.")
        sys.exit(1)
    except KeyError as e:
        logging.error(f"Expected key not found in docker inspect data: {e}")
        sys.exit(1)
    except FileNotFoundError:
        logging.error(f"File {args.add_to} not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
