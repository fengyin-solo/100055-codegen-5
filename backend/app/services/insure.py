"""财产保险业务规则：报案、定损、理赔、结案的状态流转与逐台定损口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "insure"
REQUIRED_FIELDS = ["事故名称", "出险时间", "报案人", "设备编号"]
STATUS_ORDER = ["已报案", "定损中", "待赔付", "已结案"]
# 案件级动作：动作名 -> (允许的当前状态, 目标状态)
CASE_ACTIONS = {"转入定损": ("已报案", "定损中"), "提交理赔": ("定损中", "待赔付"), "确认结案": ("待赔付", "已结案")}
DEVICE_ACTIONS = ["逐台定损", "拒赔"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_devices(raw: Any) -> list[str]:
    """把“逗号/顿号/空白分隔”或列表形式的设备编号拆成去重后的有序列表。"""
    if isinstance(raw, (list, tuple)):
        parts = [str(item) for item in raw]
    else:
        text = str(raw or "")
        for sep in ("，", "、", "；", ";", "\n", "\t", " "):
            text = text.replace(sep, ",")
        parts = text.split(",")
    seen: list[str] = []
    for part in (item.strip() for item in parts):
        if part and part not in seen:
            seen.append(part)
    return seen


def _parse_number(raw: Any) -> float | None:
    """宽松解析数字；空串、None 或解析失败都返回 None，由调用方决定怎么提示。"""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _new_device(code: str) -> dict[str, Any]:
    return {
        "设备编号": code,
        "定损状态": "待定损",
        "定损金额": None,
        "免赔比例": None,
        "免赔说明": "",
        "赔款金额": None,
        "拒赔原因": "",
    }


def _append_log(entry: dict[str, Any], operator: str, action: str, note: str) -> None:
    entry.setdefault("logs", []).append({"time": _now(), "operator": operator, "action": action, "note": note})


def _recalc(entry: dict[str, Any]) -> None:
    """赔款合计只累加已定损设备；被拒赔的设备赔款为 0，不影响其他设备。"""
    total = sum(float(dev.get("赔款金额") or 0) for dev in entry.get("devices", []) if dev.get("定损状态") == "已定损")
    entry["赔款合计"] = round(total, 2)
    entry["abnormal"] = any(dev.get("定损状态") == "已拒赔" for dev in entry.get("devices", []))


class InsureService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("案件编号", "")) or keyword in str(row.get("事故名称", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        devices = _parse_devices(values.get("设备编号"))
        if not devices:
            return None, ["设备编号"]
        rows = store.rows(MODULE)
        entry_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        reporter = str(values.get("报案人")).strip()
        entry: dict[str, Any] = {
            "id": entry_id,
            "案件编号": f"INSU-{entry_id:04d}",
            "事故名称": str(values.get("事故名称")).strip(),
            "出险时间": str(values.get("出险时间")).strip(),
            "报案人": reporter,
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
            # 一次事故涉及多台设备时合并成一案，设备逐台定损
            "devices": [_new_device(code) for code in devices],
            "赔款合计": 0,
            "logs": [],
        }
        _append_log(entry, reporter, "登记报案", f"出险报案，涉及设备 {len(devices)} 台，合并为一案")
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"保险案件 {entry_id} 不存在或已归档"
        if entry.get("status") == STATUS_ORDER[-1]:
            return None, f"案件 {entry.get('案件编号')} 已结案，不能再改回定损中，所有记录已封存"
        operator = str(values.get("operator") or "").strip()
        if not operator:
            return None, "请填写操作人：状态流转必须留下操作人与时间"
        if action in CASE_ACTIONS:
            return self._run_case_action(entry, action, operator)
        if action in DEVICE_ACTIONS:
            return self._run_device_action(entry, action, operator, values)
        return None, f"动作「{action}」不属于财产保险可执行范围"

    def _run_case_action(self, entry: dict[str, Any], action: str, operator: str) -> tuple[dict[str, Any] | None, str]:
        source, target = CASE_ACTIONS[action]
        current = str(entry.get("status"))
        if current != source:
            return None, f"案件当前状态为「{current}」，不能执行「{action}」（需处于「{source}」）"
        if action == "提交理赔":
            undone = [str(dev.get("设备编号")) for dev in entry.get("devices", []) if dev.get("定损状态") == "待定损"]
            if undone:
                return None, f"设备 {'、'.join(undone)} 尚未完成定损，逐台定损或拒赔后才能提交理赔"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        _recalc(entry)
        _append_log(entry, operator, action, f"案件状态由「{source}」流转为「{target}」，赔款合计 {entry['赔款合计']} 元")
        return entry, f"案件已{action}，当前状态：{target}"

    def _run_device_action(
        self, entry: dict[str, Any], action: str, operator: str, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") != "定损中":
            return None, f"案件当前状态为「{entry.get('status')}」，只有定损中的案件才能逐台定损或拒赔"
        code = str(values.get("设备编号") or "").strip()
        device = next((dev for dev in entry.get("devices", []) if str(dev.get("设备编号")) == code), None)
        if device is None:
            return None, f"设备 {code or '（未填写）'} 不在案件 {entry.get('案件编号')} 的出险设备清单里"
        if action == "拒赔":
            reason = str(values.get("拒赔原因") or "").strip()
            if not reason:
                return None, f"拒赔设备 {code} 必须写明拒赔原因，否则无法向报案人交代"
            device["定损状态"] = "已拒赔"
            device["拒赔原因"] = reason
            device["赔款金额"] = 0
            _recalc(entry)
            _append_log(entry, operator, "拒赔", f"设备 {code} 拒赔：{reason}；仅影响该设备，其余设备继续定损")
            return entry, f"设备 {code} 已拒赔，仅该设备赔款归零"
        amount = _parse_number(values.get("定损金额"))
        if amount is None or amount < 0:
            return None, f"设备 {code} 的定损金额必须是不小于 0 的数字"
        ratio = _parse_number(values.get("免赔比例"))
        note = str(values.get("免赔说明") or "").strip()
        if ratio is None:
            if not note:
                return None, f"设备 {code} 的免赔比例没写清楚，请在免赔说明中写明原因（如保单未约定免赔、条款待核对）"
            ratio = 0.0
        elif not 0 <= ratio <= 100:
            return None, f"设备 {code} 的免赔比例必须在 0 到 100 之间"
        payout = round(amount * (1 - ratio / 100), 2)
        device["定损状态"] = "已定损"
        device["定损金额"] = amount
        device["免赔比例"] = ratio
        device["免赔说明"] = note
        device["赔款金额"] = payout
        device["拒赔原因"] = ""
        _recalc(entry)
        _append_log(entry, operator, "逐台定损", f"设备 {code} 定损 {amount} 元，免赔 {ratio}%，赔款 {payout} 元")
        return entry, f"设备 {code} 定损完成，赔款 {payout} 元"
