import yaml
import jinja2
from pprint import pprint
from datetime import datetime
from nornir import InitNornir
from nornir.plugins.functions.text import print_result
from nornir.plugins.tasks.files import write_file
from nornir.plugins.tasks.networking import napalm_configure
from nornir.plugins.tasks.networking import napalm_get
from nornir.plugins.tasks.networking import netmiko_send_config
from nornir.plugins.tasks.text import template_file
from nornir.plugins.tasks.data import load_yaml

nr = InitNornir(config_file="config.yaml")

time = datetime.now().strftime("%d-%m-%Y_%I-%M-%S_%p")


def backup_config(task):
    # gatters > https://napalm.readthedocs.io/en/latest/support/index.html#getters-support-matrix
    # https://napalm.readthedocs.io/en/latest/base.html#

    r = task.run(
        task=napalm_get,
        name=f"Backing up running configuration for {task.host}",
        getters=["config"], full=False, retrieve="running"
    )
    # napalm_get returns config as dictionary, config as text can be extracted from ["config"] getter
    # via ["running"] key or ["startup"] for startup config and ["candidate"] for candidate
    # candidate config support need to be configured on device
    # Nornir uses result class to access individual tasks and their data
    task.host["running_config"] = r.result["config"]["running"]

    r = task.run(
        task=napalm_get,
        name=f"Backing up startup configuration for {task.host}",
        getters=["config"], full=False, retrieve="startup"
    )
    task.host["startup_config"] = r.result["config"]["startup"]

    task.run(
        task=write_file,
        name="Writing backup files of running config to disk...",
        filename=f'./backups/{time}_running_{task.host}.txt',
        content=task.host["running_config"]
    )
    task.run(
        task=write_file,
        name="Writing backup files of startup config to disk...",
        filename=f'./backups/{time}_startup_{task.host}.txt',
        content=task.host["startup_config"]
    )


def render_config(task):
    r = task.run(
        task=template_file,
        name="Base Template Configuration",
        template="int_config.j2",
        path="./templates",
        **task.host,
    )
    task.host["config"] = r.result


def push_config_with_napalm(task):
    config = task.host["config"]
    task.run(
        task=napalm_configure,
        name="Deploy Configuration",
        configuration=config,
        replace=False,  # if set to "True", full configuration is required,
        # also cisco archive must be pre configured
        dry_run=False
    )


def push_config_with_netmiko(task):
    # there is need to use Netmiko instead of Napalm in my case because
    # my Cisco IOU image does not work with napalm when pushing config,
    # there is problem with Napalm built in regex parser,
    # probably IOU device "output" does not match pattern like proper Cisco real device
    # or proper Cisco image and there is mismatch in output and that what Napalm parser
    # is expecting. Probably vIOS works flawless, but IOU is less hardware hungry.
    config = task.host["config"]
    task.run(
        task=netmiko_send_config,
        name="Deploy Configuration",
        config_commands=config
    )


def ospf_config(task):
    yaml_data = task.run(
        task=load_yaml,
        file=f"./inventory/ospf_v3/{task.host}_ospf_v3.yaml",
        # file=f"{task.host.name}.yaml" for host only data, easy access thorough Nornir inventory
    )

    ospf = yaml_data.result
    # yaml data must be unwrapped by ".result"

    r = task.run(
        task=template_file,
        path="./templates",
        template="ospf_config.j2",
        ospf=ospf  # additional argument passed to task
        # data form yaml_data.result is accessible thorough ospf key with assigned values
    )
    task.host["ospf_config"] = r.result

    config = task.host["ospf_config"]

    task.run(
        task=netmiko_send_config,
        name="Deploy Configuration",
        config_commands=config
    )


def main():
    # inventory = nr.inventory.get_inventory_dict()  # print Nornir inventory
    # pprint(inventory)

    rtr = nr.filter(name="R1")  # Nornir filter

    backup_task = rtr.run(task=backup_config)
    print_result(backup_task)

    # render_task = rtr.run(task=render_config)
    # print_result(render_task)

    # push_task = rtr.run(task=push_config_with_netmiko, num_workers=10)
    # print_result(push_task)

    ospf_task = rtr.run(task=ospf_config)
    print_result(ospf_task)


if __name__ == "__main__":
    main()
