import json
import logging
import os
from datetime import datetime

import boto3

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - best effort fallback
    ZoneInfo = None

logger = logging.getLogger()
if not logger.handlers:
    logging.basicConfig()


def _load_accounts():
    raw = os.environ.get("ACCOUNTS_JSON", "[]")
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise ValueError("ACCOUNTS_JSON must be valid JSON") from exc

    if not isinstance(data, list):
        raise ValueError("ACCOUNTS_JSON must be a JSON array")

    return data


def _env_bool(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y"}


def _normalize_tag_key(value, default):
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _load_notification_tag_keys():
    raw = os.environ.get("NOTIFICATION_TAG_KEYS", "")
    if raw is None:
        return []
    raw = raw.strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except Exception:
        data = None

    if isinstance(data, list):
        keys = []
        for item in data:
            text = str(item).strip()
            if text:
                keys.append(text)
        return keys

    return [part.strip() for part in raw.split(",") if part.strip()]


def _load_settings():
    schedule_value = os.environ.get("TAG_SCHEDULE_VALUE")
    if schedule_value is None:
        schedule_value = "True"
    else:
        schedule_value = schedule_value.strip()

    return {
        "timezone": (os.environ.get("TIMEZONE", "Asia/Seoul").strip() or "Asia/Seoul"),
        "enable_ec2": _env_bool("ENABLE_EC2", True),
        "enable_rds": _env_bool("ENABLE_RDS", False),
        "enable_asg": _env_bool("ENABLE_ASG", False),
        "tag_schedule_key": _normalize_tag_key(os.environ.get("TAG_SCHEDULE_KEY"), "Schedule"),
        "tag_schedule_value": schedule_value,
        "tag_start_key": _normalize_tag_key(os.environ.get("TAG_START_KEY"), "Schedule_Start"),
        "tag_stop_key": _normalize_tag_key(os.environ.get("TAG_STOP_KEY"), "Schedule_Stop"),
        "tag_weekday_key": _normalize_tag_key(os.environ.get("TAG_WEEKDAY_KEY"), "Schedule_Weekend"),
        "tag_asg_min_key": _normalize_tag_key(os.environ.get("TAG_ASG_MIN_KEY"), "Schedule_Asg_Min"),
        "tag_asg_max_key": _normalize_tag_key(os.environ.get("TAG_ASG_MAX_KEY"), "Schedule_Asg_Max"),
        "tag_asg_desired_key": _normalize_tag_key(
            os.environ.get("TAG_ASG_DESIRED_KEY"),
            "Schedule_Asg_Desired",
        ),
        "notification_tag_keys": _load_notification_tag_keys(),
    }


def _configure_logging():
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    return level_name


def _parse_int(value):
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _parse_time(value):
    text = str(value).strip()
    if ":" in text:
        parts = text.split(":", 1)
        hour = int(parts[0])
        minute = int(parts[1])
    else:
        hour = int(text)
        minute = 0

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Invalid time value: {value}")

    return hour * 60 + minute


def _should_run(now_minutes, start_minutes, stop_minutes):
    if start_minutes == stop_minutes:
        return False
    if start_minutes < stop_minutes:
        return start_minutes <= now_minutes < stop_minutes
    return now_minutes >= start_minutes or now_minutes < stop_minutes


def _tag_value_match(actual, expected):
    if actual is None:
        return False
    if expected is None:
        return True
    expected = expected.strip()
    if expected == "":
        return True
    return actual.strip().lower() == expected.lower()


def _parse_weekdays(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = [p.strip().lower() for p in text.split(",") if p.strip()]
    return set(parts) if parts else None


def _weekday_token(now):
    # Mon, Tue, Wed, Thu, Fri, Sat, Sun
    return now.strftime("%a").lower()


def _tags_to_dict(tags):
    return {tag.get("Key"): tag.get("Value") for tag in tags or [] if tag.get("Key")}


def _extract_notification_tags(tags, keys):
    if not keys:
        return ""
    pairs = []
    for key in keys:
        value = tags.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        pairs.append(f"{key}={text}")
    return ", ".join(pairs)


def _build_change(action, resource_type, resource_id, tags, notify_tag_keys, details=None):
    return {
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details,
        "tag_summary": _extract_notification_tags(tags, notify_tag_keys),
    }


def _evaluate_schedule(tags, config, now_minutes, now_token):
    if not _tag_value_match(tags.get(config["schedule_key"]), config["schedule_value"]):
        return None

    schedule_weekend = _parse_weekdays(tags.get(config["weekday_key"]))
    if not schedule_weekend:
        return None

    if now_token not in schedule_weekend:
        return None

    start_value = tags.get(config["start_key"])
    stop_value = tags.get(config["stop_key"])
    if start_value is None or stop_value is None:
        return None

    try:
        start_minutes = _parse_time(start_value)
        stop_minutes = _parse_time(stop_value)
    except ValueError:
        return None

    return _should_run(now_minutes, start_minutes, stop_minutes)


def _assume_role(session, account_id, role_value):
    if role_value.startswith("arn:"):
        role_arn = role_value
    else:
        role_arn = f"arn:aws:iam::{account_id}:role/{role_value}"

    sts = session.client("sts")
    resp = sts.assume_role(RoleArn=role_arn, RoleSessionName="scheduler-lambda")
    creds = resp["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )


def _send_teams(webhook, message):
    if not webhook:
        return
    payload = json.dumps({"text": message}).encode("utf-8")
    _post_json(webhook, payload)


def _send_slack(webhook, message):
    if not webhook:
        return
    payload = json.dumps({"text": message}).encode("utf-8")
    _post_json(webhook, payload)


def _send_telegram(token, chat_id, message):
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    _post_json(url, payload)


def _post_json(url, payload):
    from urllib import request

    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=10):
        return


def _format_action_label(action):
    if not action:
        return ""
    mapping = {
        "start": "🟢 Start",
        "stop": "🔴 Stop",
        "scale": "⚙️ Scale",
    }
    return mapping.get(action, str(action))


def _format_resource_label(resource_type):
    if not resource_type:
        return ""
    mapping = {
        "ec2": "EC2",
        "rds-instance": "RDS-Instance",
        "rds-cluster": "RDS-Cluster",
        "asg": "ASG",
    }
    return mapping.get(resource_type, str(resource_type))


def _render_table(headers, rows):
    def _display_width(text):
        width = 0
        for ch in str(text):
            width += 1 if ord(ch) < 128 else 2
        return width

    def _pad_cell(text, width):
        text = str(text)
        pad = width - _display_width(text)
        if pad <= 0:
            return text
        return text + (" " * pad)

    widths = [_display_width(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], _display_width(cell))

    def _line(values):
        return "| " + " | ".join(
            _pad_cell(values[idx], widths[idx]) for idx in range(len(values))
        ) + " |"

    lines = [
        _line(headers),
        "| " + " | ".join("-" * widths[idx] for idx in range(len(headers))) + " |",
    ]
    for row in rows:
        lines.append(_line(row))
    return lines


def _build_message(account, changes, now):
    header = f"[Scheduler] {account.get('description', account.get('account_id', 'account'))}"
    lines = [header, f"Time: {now.strftime('%Y-%m-%d %H:%M %Z')}"]
    account_id = account.get("account_id")
    region = account.get("region")
    if account_id or region:
        account_parts = []
        if account_id:
            account_parts.append(f"Account: {account_id}")
        if region:
            account_parts.append(f"Region: {region}")
        lines.append(" | ".join(account_parts))

    lines.append(f"Changes ({len(changes)}):")
    if changes:
        headers = ["Action", "Type", "Id", "Tags/Details"]
        rows = []
        for change in changes:
            details = change.get("details") or ""
            tags = change.get("tag_summary") or ""
            extra = "; ".join(part for part in (details, tags) if part)
            rows.append(
                [
                    _format_action_label(change.get("action")),
                    _format_resource_label(change.get("resource_type")),
                    change.get("resource_id") or "",
                    extra,
                ]
            )
        lines.append("```")
        lines.extend(_render_table(headers, rows))
        lines.append("```")
    return "\n".join(lines)


def _maybe_send_notifications(account, changes, now):
    if not changes:
        return

    message = _build_message(account, changes, now)
    _send_teams(account.get("teams_webhook"), message)
    _send_slack(account.get("slack_webhook"), message)
    _send_telegram(
        account.get("telegram_bot_token"),
        account.get("telegram_chat_id"),
        message,
    )


def _validate_account(account):
    for key in ("account_id", "region", "iam_role"):
        if not account.get(key):
            raise ValueError(f"Account entry missing required field: {key}")


def _candidate_tag_values(value):
    values = {value}
    lower = value.lower()
    upper = value.upper()
    values.add(lower)
    values.add(upper)
    return sorted(values)


def _collect_instances(ec2, tag_key, tag_value):
    paginator = ec2.get_paginator("describe_instances")
    filters = []
    if tag_key:
        if tag_value is not None and tag_value.strip():
            filters.append({"Name": f"tag:{tag_key}", "Values": _candidate_tag_values(tag_value)})
        else:
            filters.append({"Name": "tag-key", "Values": [tag_key]})

    paginate_kwargs = {"Filters": filters} if filters else {}
    for page in paginator.paginate(**paginate_kwargs):
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                yield instance


def _handle_instance(ec2, instance, config, now_minutes, now_token, notify_tag_keys):
    instance_id = instance["InstanceId"]
    tags = _tags_to_dict(instance.get("Tags", []))
    should_run = _evaluate_schedule(tags, config, now_minutes, now_token)
    if should_run is None:
        return None
    state = instance.get("State", {}).get("Name")

    if should_run and state == "stopped":
        ec2.start_instances(InstanceIds=[instance_id])
        return _build_change("start", "ec2", instance_id, tags, notify_tag_keys)
    if (not should_run) and state == "running":
        ec2.stop_instances(InstanceIds=[instance_id])
        return _build_change("stop", "ec2", instance_id, tags, notify_tag_keys)

    return None


def _collect_rds_instances(rds):
    paginator = rds.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for instance in page.get("DBInstances", []):
            yield instance


def _collect_rds_clusters(rds):
    paginator = rds.get_paginator("describe_db_clusters")
    for page in paginator.paginate():
        for cluster in page.get("DBClusters", []):
            yield cluster


def _list_rds_tags(rds, arn):
    resp = rds.list_tags_for_resource(ResourceName=arn)
    return {tag.get("Key"): tag.get("Value") for tag in resp.get("TagList", []) if tag.get("Key")}

def _collect_autoscaling_groups(asg):
    paginator = asg.get_paginator("describe_auto_scaling_groups")
    for page in paginator.paginate():
        for group in page.get("AutoScalingGroups", []):
            yield group


def _asg_sizes(group):
    return {
        "MinSize": _parse_int(group.get("MinSize")),
        "MaxSize": _parse_int(group.get("MaxSize")),
        "DesiredCapacity": _parse_int(group.get("DesiredCapacity")),
    }


def _build_asg_target(current, tags, asg_keys):
    target = {
        "MinSize": _parse_int(tags.get(asg_keys["min_key"])),
        "MaxSize": _parse_int(tags.get(asg_keys["max_key"])),
        "DesiredCapacity": _parse_int(tags.get(asg_keys["desired_key"])),
    }
    for key in ("MinSize", "MaxSize", "DesiredCapacity"):
        if target[key] is None:
            target[key] = current.get(key)
    return target


def _sanitize_asg_target(target):
    min_size = target.get("MinSize")
    max_size = target.get("MaxSize")
    desired = target.get("DesiredCapacity")
    if min_size is None or max_size is None or desired is None:
        return None
    if min_size < 0 or max_size < 0 or desired < 0:
        return None
    if min_size > max_size:
        return None
    if desired < min_size:
        desired = min_size
    if desired > max_size:
        desired = max_size
    return {"MinSize": min_size, "MaxSize": max_size, "DesiredCapacity": desired}


def _handle_autoscaling_group(
    asg,
    group,
    tag_config,
    asg_keys,
    now_minutes,
    now_token,
    notify_tag_keys,
):
    name = group.get("AutoScalingGroupName")
    if not name:
        return None

    tags = _tags_to_dict(group.get("Tags", []))
    should_run = _evaluate_schedule(tags, tag_config, now_minutes, now_token)
    if should_run is None:
        return None

    current = _asg_sizes(group)
    if current["MinSize"] is None or current["MaxSize"] is None or current["DesiredCapacity"] is None:
        return None
    if (
        tags.get(asg_keys["min_key"]) is None
        or tags.get(asg_keys["max_key"]) is None
        or tags.get(asg_keys["desired_key"]) is None
    ):
        return None

    if should_run:
        target = _sanitize_asg_target(_build_asg_target(current, tags, asg_keys))
        if not target:
            return None
        if (
            target["MinSize"] == current["MinSize"]
            and target["MaxSize"] == current["MaxSize"]
            and target["DesiredCapacity"] == current["DesiredCapacity"]
        ):
            return None
        asg.update_auto_scaling_group(AutoScalingGroupName=name, **target)
        details = (
            f"min={target['MinSize']} "
            f"max={target['MaxSize']} desired={target['DesiredCapacity']}"
        )
        return _build_change("scale", "asg", name, tags, notify_tag_keys, details=details)

    if current["MinSize"] == 0 and current["MaxSize"] == 0 and current["DesiredCapacity"] == 0:
        return None

    asg.update_auto_scaling_group(
        AutoScalingGroupName=name,
        MinSize=0,
        MaxSize=0,
        DesiredCapacity=0,
    )
    return _build_change(
        "scale",
        "asg",
        name,
        tags,
        notify_tag_keys,
        details="min=0 max=0 desired=0",
    )


def _handle_rds_instance(rds, instance, config, now_minutes, now_token, notify_tag_keys):
    if instance.get("DBClusterIdentifier"):
        return None
    arn = instance.get("DBInstanceArn")
    if not arn:
        return None

    tags = _list_rds_tags(rds, arn)
    should_run = _evaluate_schedule(tags, config, now_minutes, now_token)
    if should_run is None:
        return None

    status = instance.get("DBInstanceStatus")
    identifier = instance.get("DBInstanceIdentifier")
    if should_run and status == "stopped":
        rds.start_db_instance(DBInstanceIdentifier=identifier)
        return _build_change(
            "start",
            "rds-instance",
            identifier,
            tags,
            notify_tag_keys,
        )
    if (not should_run) and status == "available":
        rds.stop_db_instance(DBInstanceIdentifier=identifier)
        return _build_change(
            "stop",
            "rds-instance",
            identifier,
            tags,
            notify_tag_keys,
        )
    return None


def _handle_rds_cluster(rds, cluster, config, now_minutes, now_token, notify_tag_keys):
    arn = cluster.get("DBClusterArn")
    if not arn:
        return None

    tags = _list_rds_tags(rds, arn)
    should_run = _evaluate_schedule(tags, config, now_minutes, now_token)
    if should_run is None:
        return None

    status = cluster.get("Status")
    identifier = cluster.get("DBClusterIdentifier")
    if should_run and status == "stopped":
        rds.start_db_cluster(DBClusterIdentifier=identifier)
        return _build_change(
            "start",
            "rds-cluster",
            identifier,
            tags,
            notify_tag_keys,
        )
    if (not should_run) and status == "available":
        rds.stop_db_cluster(DBClusterIdentifier=identifier)
        return _build_change(
            "stop",
            "rds-cluster",
            identifier,
            tags,
            notify_tag_keys,
        )
    return None


def handler(event, context):
    if ZoneInfo is None:
        raise RuntimeError("ZoneInfo not available")

    settings = _load_settings()
    log_level = _configure_logging()

    try:
        tz = ZoneInfo(settings["timezone"])
    except Exception as exc:
        raise RuntimeError("Failed to load timezone") from exc

    now = datetime.now(tz=tz)
    now_minutes = now.hour * 60 + now.minute
    now_token = _weekday_token(now)

    logger.info(
        "scheduler start log_level=%s timezone=%s now=%s",
        log_level,
        settings["timezone"],
        now.strftime("%Y-%m-%d %H:%M:%S %Z"),
    )

    accounts = _load_accounts()
    base_session = boto3.Session()

    summary = []

    tag_config = {
        "schedule_key": settings["tag_schedule_key"],
        "schedule_value": settings["tag_schedule_value"],
        "start_key": settings["tag_start_key"],
        "stop_key": settings["tag_stop_key"],
        "weekday_key": settings["tag_weekday_key"],
    }
    notify_tag_keys = settings["notification_tag_keys"]
    asg_config = {
        "min_key": settings["tag_asg_min_key"],
        "max_key": settings["tag_asg_max_key"],
        "desired_key": settings["tag_asg_desired_key"],
    }

    for account in accounts:
        _validate_account(account)
        target_session = _assume_role(base_session, account["account_id"], account["iam_role"])
        changes = []

        needs_ec2 = settings["enable_ec2"]
        needs_rds = settings["enable_rds"]
        needs_asg = settings["enable_asg"]

        ec2 = target_session.client("ec2", region_name=account["region"]) if needs_ec2 else None
        rds = target_session.client("rds", region_name=account["region"]) if needs_rds else None
        asg = (
            target_session.client("autoscaling", region_name=account["region"])
            if needs_asg
            else None
        )

        ec2_scanned = 0
        ec2_changes = 0
        if settings["enable_ec2"] and ec2:
            for instance in _collect_instances(
                ec2,
                tag_config["schedule_key"],
                tag_config["schedule_value"],
            ):
                ec2_scanned += 1
                change = _handle_instance(
                    ec2,
                    instance,
                    tag_config,
                    now_minutes,
                    now_token,
                    notify_tag_keys,
                )
                if change:
                    ec2_changes += 1
                    changes.append(change)

        rds_instance_scanned = 0
        rds_instance_changes = 0
        rds_cluster_scanned = 0
        rds_cluster_changes = 0
        if settings["enable_rds"] and rds:
            for instance in _collect_rds_instances(rds):
                rds_instance_scanned += 1
                change = _handle_rds_instance(
                    rds,
                    instance,
                    tag_config,
                    now_minutes,
                    now_token,
                    notify_tag_keys,
                )
                if change:
                    rds_instance_changes += 1
                    changes.append(change)
            for cluster in _collect_rds_clusters(rds):
                rds_cluster_scanned += 1
                change = _handle_rds_cluster(
                    rds,
                    cluster,
                    tag_config,
                    now_minutes,
                    now_token,
                    notify_tag_keys,
                )
                if change:
                    rds_cluster_changes += 1
                    changes.append(change)

        asg_scanned = 0
        asg_changes = 0
        if settings["enable_asg"] and asg:
            for group in _collect_autoscaling_groups(asg):
                asg_scanned += 1
                change = _handle_autoscaling_group(
                    asg,
                    group,
                    tag_config,
                    asg_config,
                    now_minutes,
                    now_token,
                    notify_tag_keys,
                )
                if change:
                    asg_changes += 1
                    changes.append(change)

        logger.info(
            "account=%s region=%s ec2_scanned=%d ec2_changes=%d "
            "rds_instances_scanned=%d rds_instances_changes=%d "
            "rds_clusters_scanned=%d rds_clusters_changes=%d "
            "asg_scanned=%d asg_changes=%d",
            account.get("account_id"),
            account.get("region"),
            ec2_scanned,
            ec2_changes,
            rds_instance_scanned,
            rds_instance_changes,
            rds_cluster_scanned,
            rds_cluster_changes,
            asg_scanned,
            asg_changes,
        )

        if changes:
            logger.info("account=%s changes=%s", account.get("account_id"), changes)
        else:
            logger.info("account=%s no changes", account.get("account_id"))

        _maybe_send_notifications(account, changes, now)
        summary.append({"account": account.get("account_id"), "changes": changes})

    return {"status": "ok", "summary": summary}
