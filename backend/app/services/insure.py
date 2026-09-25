"""财产保险业务规则：报案、定损、理赔、结案的状态机与赔款口径都收在这里。

一个案件对应一次事故；一次事故涉及多台设备时合并为一案，设备明细逐台定损。
赔款金额一律在服务端按「定损金额 × (1 − 免赔比例/100)」计算并写回数据仓库，
前端只负责展示，刷新后重新读取，不会回到旧值。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "insure"
REQUIRED_FIELDS = ["事故名称", "出险时间", "报案人"]
STATUS_ORDER = ["已报案", "定损中", "待赔付", "已结案"]
CASE_ACTIONS = {"转入定损": "定损中", "提交理赔": "待赔付", "结案": "已结案"}
ITEM_PENDING = "待定损"
ITEM_ASSESSED = "已定损"
ITEM_REJECTED = "已拒赔"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _operator(values: dict[str, Any]) -> str:
    return str(values.get("操作人") or "").strip() or "值班管理员"


def _split_devices(raw: Any) -> list[str]:
    """把“每行一台 / 逗号分隔”的设备编号输入整理成去重后的清单。"""
    if isinstance(raw, str):
        parts = re.split(r"[，,、;；\s]+", raw)
    elif isinstance(raw, (list, tuple)):
        parts = [str(item) for item in raw]
    else:
        parts = []
    devices: list[str] = []
    for part in parts:
        code = part.strip()
        if code and code not in devices:
            devices.append(code)
    return devices


def _parse_number(raw: Any) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _trail(case: dict[str, Any], operator: str, note: str) -> None:
    """每个状态变化都留下操作人与时间，事后能对上赔了多少、谁办的。"""
    case.setdefault("轨迹", []).append({
        "状态": case.get("status", ""),
        "操作人": operator,
        "时间": _now(),
        "说明": note,
    })


def _recalc(case: dict[str, Any]) -> None:
    """按设备明细重算案件合计：被拒赔的设备不贡献赔款，只影响它自己。"""
    items = case.get("items", [])
    assessed = [item for item in items if item.get("明细状态") == ITEM_ASSESSED]
    case["定损合计"] = round(sum(float(item.get("定损金额") or 0) for item in assessed), 2)
    case["赔款合计"] = round(sum(float(item.get("赔款金额") or 0) for item in assessed), 2)
    case["设备台数"] = len(items)
    case["abnormal"] = any(item.get("明细状态") == ITEM_REJECTED for item in items)


class InsureService:
    def list_cases(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("案件编号", "")) or keyword in str(row.get("事故名称", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_case(self, case_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, case_id)

    def create_case(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        devices = _split_devices(values.get("设备编号"))
        if not devices:
            return None, "缺少必填字段：设备编号（一次事故涉及多台设备时逐行或逗号分隔填写，会合并为一案再逐台定损）"
        rows = store.rows(MODULE)
        next_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        case_no = str(values.get("案件编号") or "").strip() or f"INSU-{next_id:04d}"
        if any(str(row.get("案件编号", "")) == case_no for row in rows):
            return None, f"案件编号 {case_no} 已存在，请更换编号或留空由系统生成"
        case: dict[str, Any] = {
            "id": next_id,
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
            "案件编号": case_no,
            "事故名称": str(values.get("事故名称")).strip(),
            "出险时间": str(values.get("出险时间")).strip(),
            "报案人": str(values.get("报案人")).strip(),
            "案件状态": STATUS_ORDER[0],
            "items": [
                {
                    "id": index,
                    "设备编号": code,
                    "设备名称": "",
                    "明细状态": ITEM_PENDING,
                    "定损金额": None,
                    "免赔比例": None,
                    "免赔说明": "",
                    "赔款金额": None,
                    "拒赔原因": "",
                    "定损人": "",
                    "定损时间": "",
                }
                for index, code in enumerate(devices, start=1)
            ],
            "轨迹": [],
        }
        _recalc(case)
        _trail(case, _operator(values), f"按设备编号登记出险报案，{len(devices)} 台设备合并为一案")
        rows.append(case)
        return case, f"出险报案已登记，{len(devices)} 台设备合并为案件 {case_no}"

    def run_action(self, case_id: int, action: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        case = store.find(MODULE, case_id)
        if case is None:
            return None, f"保险案件 {case_id} 不存在或已归档"
        if case.get("status") == STATUS_ORDER[-1]:
            return None, f"案件 {case.get('案件编号')} 已结案，不能再改回定损中或任何其他状态"
        if action not in CASE_ACTIONS:
            return None, f"动作「{action}」不属于财产保险可执行范围（支持：{'、'.join(CASE_ACTIONS)}）"
        target = CASE_ACTIONS[action]
        expect = STATUS_ORDER[STATUS_ORDER.index(target) - 1]
        if case.get("status") != expect:
            return None, f"案件当前状态为「{case.get('status')}」，不能执行「{action}」（需先处于「{expect}」）"
        if action == "提交理赔":
            pending = [str(item.get("设备编号", "")) for item in case.get("items", []) if item.get("明细状态") == ITEM_PENDING]
            if pending:
                return None, f"还有 {len(pending)} 台设备未定损（{'、'.join(pending)}），请逐台定损或拒赔后再提交理赔"
        operator = _operator(values)
        case["status"] = target
        case["案件状态"] = target
        case["pending"] = target != STATUS_ORDER[-1]
        notes = {
            "转入定损": "报案已受理，案件转入定损，开始逐台核定损失",
            "提交理赔": f"全部设备已定损或拒赔，提交理赔，赔款合计 {case.get('赔款合计', 0)} 元",
            "结案": f"赔款已兑付，案件结案，最终赔款 {case.get('赔款合计', 0)} 元",
        }
        _trail(case, operator, notes[action])
        return case, f"案件已{action}"

    def assess_item(self, case_id: int, item_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        case, item, error = self._locate(case_id, item_id)
        if error:
            return None, error
        status_error = self._check_case_open(case, "定损")
        if status_error:
            return None, status_error
        if item.get("明细状态") == ITEM_REJECTED:
            return None, f"设备 {item.get('设备编号')} 已被拒赔，拒赔结论只影响该台设备，不能再改为定损"
        amount_raw = values.get("定损金额")
        if amount_raw is None or str(amount_raw).strip() == "":
            return None, "定损金额未填写：定损金额是计算赔款的基础，请先核定该台设备的损失金额再提交"
        amount = _parse_number(amount_raw)
        if amount is None or amount < 0:
            return None, f"定损金额「{amount_raw}」不是有效金额，请填写不小于 0 的数字"
        ratio_raw = values.get("免赔比例")
        if ratio_raw is None or str(ratio_raw).strip() == "":
            return None, (
                "免赔比例未写清楚：赔款按「定损金额 × (1 − 免赔比例)」计算，缺少比例算不出赔款，"
                "赔多少钱会对不上。请按保单约定填写 0–100 的数值，比例依据（条款编号、特别约定）写进免赔说明"
            )
        ratio = _parse_number(ratio_raw)
        if ratio is None or not 0 <= ratio <= 100:
            return None, f"免赔比例「{ratio_raw}」不是 0–100 之间的有效数值，无法据此计算赔款，请核对保单免赔条款后重新填写"
        payout = round(amount * (1 - ratio / 100), 2)
        operator = _operator(values)
        item.update({
            "明细状态": ITEM_ASSESSED,
            "定损金额": amount,
            "免赔比例": ratio,
            "免赔说明": str(values.get("免赔说明") or "").strip(),
            "赔款金额": payout,
            "拒赔原因": "",
            "定损人": operator,
            "定损时间": _now(),
        })
        _recalc(case)
        _trail(case, operator, f"设备 {item.get('设备编号')} 完成定损：定损 {amount} 元，免赔 {ratio}%，赔款 {payout} 元")
        return case, f"设备 {item.get('设备编号')} 定损完成，赔款金额 {payout} 元"

    def reject_item(self, case_id: int, item_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        case, item, error = self._locate(case_id, item_id)
        if error:
            return None, error
        status_error = self._check_case_open(case, "拒赔")
        if status_error:
            return None, status_error
        if item.get("明细状态") == ITEM_REJECTED:
            return None, f"设备 {item.get('设备编号')} 已经是拒赔状态，无需重复操作"
        reason = str(values.get("拒赔原因") or "").strip()
        if not reason:
            return None, "拒赔必须写明拒赔原因，否则设备责任人无法核对，案件也不能归档"
        operator = _operator(values)
        item.update({
            "明细状态": ITEM_REJECTED,
            "赔款金额": 0,
            "拒赔原因": reason,
            "定损人": operator,
            "定损时间": _now(),
        })
        _recalc(case)
        _trail(case, operator, f"设备 {item.get('设备编号')} 被拒赔：{reason}（仅该台设备受影响，其余设备继续定损）")
        return case, f"设备 {item.get('设备编号')} 已拒赔，仅该台设备受影响，案件其余设备照常流转"

    def _locate(self, case_id: int, item_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
        case = store.find(MODULE, case_id)
        if case is None:
            return None, None, f"保险案件 {case_id} 不存在或已归档"
        for item in case.get("items", []):
            if int(item.get("id", 0)) == item_id:
                return case, item, ""
        return case, None, f"案件 {case.get('案件编号')} 中没有编号为 {item_id} 的设备明细"

    def _check_case_open(self, case: dict[str, Any] | None, action: str) -> str:
        """只有定损中的案件允许逐台定损/拒赔；已结案的一律锁死。"""
        if case is None:
            return "案件不存在"
        status = case.get("status")
        if status == STATUS_ORDER[-1]:
            return f"案件 {case.get('案件编号')} 已结案，不能再改回定损中，设备{action}已锁定"
        if status == "待赔付":
            return f"案件 {case.get('案件编号')} 已提交理赔，赔款金额已锁定，不能再{action}"
        if status != "定损中":
            return f"案件 {case.get('案件编号')} 仍处于「{status}」，请先执行「转入定损」再逐台{action}"
        return ""
