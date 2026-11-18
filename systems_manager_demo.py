#!/usr/bin/env python3
"""AWS Systems Manager demo — inventory, Parameter Store, Run Command, patch report.

Usage:
    python systems_manager_demo.py --demo            # offline walkthrough (no AWS needed)
    python systems_manager_demo.py --inventory       # list managed instances (real AWS)
    python systems_manager_demo.py --param /prod/app/db-host
    python systems_manager_demo.py --put-param /demo/app/mode plain "canary"
    python systems_manager_demo.py --run "df -h /" --targets Role=web
    python systems_manager_demo.py --patch-report

Real mode needs AWS credentials with ssm:* permissions and instances running
the SSM Agent with the AmazonSSMManagedInstanceCore instance profile.
"""

import argparse
import json
import os
import sys
import time

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")


# ---------------------------------------------------------------------------
# Demo data (offline mode — mirrors what the real API returns)
# ---------------------------------------------------------------------------
DEMO_INSTANCES = [
    {"InstanceId": "i-0aaa1111web01", "PlatformName": "Amazon Linux",
     "PlatformVersion": "2023", "AgentVersion": "3.3.987.0",
     "PingStatus": "Online", "Tags": {"Role": "web", "PatchGroup": "web"}},
    {"InstanceId": "i-0bbb2222web02", "PlatformName": "Amazon Linux",
     "PlatformVersion": "2023", "AgentVersion": "3.3.987.0",
     "PingStatus": "Online", "Tags": {"Role": "web", "PatchGroup": "web"}},
    {"InstanceId": "i-0ccc3333db01", "PlatformName": "Ubuntu",
     "PlatformVersion": "22.04", "AgentVersion": "3.3.987.0",
     "PingStatus": "Online", "Tags": {"Role": "db", "PatchGroup": "db"}},
    {"InstanceId": "i-0ddd4444old01", "PlatformName": "Amazon Linux 2",
     "PlatformVersion": "2", "AgentVersion": "3.2.190.0",
     "PingStatus": "ConnectionLost", "Tags": {"Role": "web", "PatchGroup": "web"}},
]

DEMO_PARAMETERS = {
    "/prod/app/db-host": {"Type": "String", "Value": "prod-db.cluster-xyz.ap-southeast-1.rds.amazonaws.com"},
    "/prod/app/db-password": {"Type": "SecureString", "Value": "•••••••• (decrypt with KMS)"},
    "/prod/app/mode": {"Type": "String", "Value": "production"},
}

DEMO_PATCH_STATES = {
    "i-0aaa1111web01": {"Missing": 0, "Installed": 142, "Failed": 0},
    "i-0bbb2222web02": {"Missing": 2, "Installed": 140, "Failed": 0},
    "i-0ccc3333db01": {"Missing": 0, "Installed": 98, "Failed": 0},
    "i-0ddd4444old01": {"Missing": 37, "Installed": 61, "Failed": 3},
}


def demo_inventory() -> None:
    print("== Managed instances (demo) ==")
    online = [i for i in DEMO_INSTANCES if i["PingStatus"] == "Online"]
    print(f"{len(DEMO_INSTANCES)} registered, {len(online)} online")
    for inst in DEMO_INSTANCES:
        status = "✅" if inst["PingStatus"] == "Online" else "❌"
        print(f"  {status} {inst['InstanceId']}  {inst['PlatformName']} {inst['PlatformVersion']}"
              f"  agent {inst['AgentVersion']}  tags={inst['Tags']}")
    if len(online) != len(DEMO_INSTANCES):
        print("  ⚠️  i-0ddd4444old01 is ConnectionLost — check the agent, IAM role, "
              "or VPC endpoints (no NAT, no ssm endpoints = can't phone home).")


def demo_parameter(name: str) -> None:
    print(f"== Parameter {name} (demo) ==")
    param = DEMO_PARAMETERS.get(name)
    if not param:
        print(f"  Parameter {name} not found.")
        return
    print(f"  Type:  {param['Type']}")
    print(f"  Value: {param['Value']}")
    if param["Type"] == "SecureString":
        print("  (Real mode: pass WithDecryption=True — value is KMS-encrypted at rest.)")


def demo_run_command(command: str, target: str) -> None:
    key, _, value = target.partition("=")
    targets = [i for i in DEMO_INSTANCES
               if i["Tags"].get(key) == value and i["PingStatus"] == "Online"]
    print(f"== Run Command (demo): {command!r} on tag {key}={value} ==")
    print(f"  Command ID: demo-cmd-2026-11-16  |  targets: {len(targets)}")
    for inst in targets:
        print(f"  ✅ {inst['InstanceId']}: exit 0 — "
              f"Filesystem  Size  Used  Avail  Use%  Mounted on\n"
              f"     /dev/xvda1   20G  8.1G   12G   41%  /")
    print("  (Real mode polls list_command_invocations until every target "
          "reports Success / Failed / TimedOut.)")


def demo_patch_report() -> None:
    print("== Patch compliance (demo) ==")
    total_missing = sum(s["Missing"] for s in DEMO_PATCH_STATES.values())
    for iid, state in DEMO_PATCH_STATES.items():
        flag = "⚠️" if state["Missing"] > 0 or state["Failed"] > 0 else "✅"
        print(f"  {flag} {iid}: missing={state['Missing']} installed={state['Installed']} "
              f"failed={state['Failed']}")
    print(f"  Total missing patches across fleet: {total_missing}")
    if total_missing:
        print("  👉 i-0ddd4444old01 needs attention: 37 missing + 3 failed — "
              "check its patch baseline and maintenance window assignment.")


def demo() -> None:
    print("AWS Systems Manager — offline demo (no AWS calls)\n")
    demo_inventory()
    print()
    demo_parameter("/prod/app/db-password")
    print()
    demo_run_command("df -h /", "Role=web")
    print()
    demo_patch_report()
    print("\nDone. Run with --inventory / --run / --patch-report against real AWS.")


# ---------------------------------------------------------------------------
# Real AWS mode (boto3)
# ---------------------------------------------------------------------------
def _client():
    import boto3  # noqa: PLC0415  (only needed for real mode)
    return boto3.client("ssm", region_name=REGION)


def real_inventory() -> None:
    ssm = _client()
    paginator = ssm.get_paginator("describe_instance_information")
    count = 0
    for page in paginator.paginate():
        for inst in page["InstanceInformationList"]:
            count += 1
            print(f"  {inst['InstanceId']}  {inst.get('PlatformName')} "
                  f"{inst.get('PlatformVersion')}  agent {inst.get('AgentVersion')}  "
                  f"{inst.get('PingStatus')}")
    print(f"{count} managed instance(s) in {REGION}.")


def real_get_parameter(name: str) -> None:
    ssm = _client()
    resp = ssm.get_parameter(Name=name, WithDecryption=True)
    param = resp["Parameter"]
    print(json.dumps({"Name": param["Name"], "Type": param["Type"],
                      "Value": param["Value"]}, indent=2))


def real_put_parameter(name: str, ptype: str, value: str) -> None:
    ssm = _client()
    kwargs = {"Name": name, "Value": value, "Type": ptype, "Overwrite": True}
    if ptype == "SecureString":
        kwargs["Tier"] = "Standard"
    ssm.put_parameter(**kwargs)
    print(f"Stored {name} ({ptype}).")


def real_run_command(command: str, target: str, timeout: int = 120) -> int:
    ssm = _client()
    key, _, value = target.partition("=")
    resp = ssm.send_command(
        DocumentName="AWS-RunShellScript",
        Targets=[{"Key": f"tag:{key}", "Values": [value]}],
        Parameters={"commands": [command]},
        TimeoutSeconds=timeout,
    )
    command_id = resp["Command"]["CommandId"]
    print(f"Command {command_id} sent to tag {key}={value}; polling...")
    deadline = time.time() + timeout + 60
    while time.time() < deadline:
        inv = ssm.list_command_invocations(CommandId=command_id, Details=True)
        invocations = inv["CommandInvocations"]
        if invocations and all(i["Status"] not in ("Pending", "InProgress", "Delayed")
                               for i in invocations):
            for i in invocations:
                print(f"  {i['InstanceId']}: {i['Status']} "
                      f"(exit {i.get('CommandPlugins', [{}])[0].get('ResponseCode', '?')})")
                print(f"    {i['CommandPlugins'][0].get('Output', '').strip()}")
            return 0 if all(i["Status"] == "Success" for i in invocations) else 1
        time.sleep(5)
    print("Timed out waiting for invocations.")
    return 2


def real_patch_report() -> None:
    ssm = _client()
    paginator = ssm.get_paginator("describe_instance_information")
    ids = [i["InstanceId"] for page in paginator.paginate()
           for i in page["InstanceInformationList"]]
    for iid in ids:
        state = ssm.describe_instance_patch_states(InstanceIds=[iid])["InstancePatchStates"][0]
        print(f"  {iid}: missing={state.get('MissingCount')} "
              f"installed={state.get('InstalledCount')} failed={state.get('FailedCount')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="offline walkthrough")
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--param", metavar="NAME", help="read a parameter")
    parser.add_argument("--put-param", nargs=3, metavar=("NAME", "TYPE", "VALUE"),
                        help="store a parameter (TYPE: String|SecureString)")
    parser.add_argument("--run", metavar="COMMAND", help="Run Command shell command")
    parser.add_argument("--targets", default="Role=web",
                        help="tag filter for --run, e.g. Role=web (default)")
    parser.add_argument("--patch-report", action="store_true")
    args = parser.parse_args(argv)

    if args.demo:
        demo()
        return 0
    if args.inventory:
        real_inventory()
        return 0
    if args.param:
        real_get_parameter(args.param)
        return 0
    if args.put_param:
        real_put_parameter(*args.put_param)
        return 0
    if args.run:
        return real_run_command(args.run, args.targets)
    if args.patch_report:
        real_patch_report()
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
