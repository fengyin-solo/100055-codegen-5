"""财产保险接口：出险报案、逐台定损、提交理赔与结案，每个状态都留操作人与时间。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.insure import InsureService

router = APIRouter(prefix="/api/insure", tags=["财产保险"])

service = InsureService()


@router.get("", response_model=PageResult[dict])
def list_cases(
    keyword: str | None = Query(default=None, description="按案件编号或事故名称检索"),
    status: str | None = Query(default=None, description="已报案、定损中、待赔付、已结案"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按编号/名称与状态过滤保险案件列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_cases(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_cases() -> dict[str, Any]:
    """导出财产保险案件清单：返回当前全量数据。"""
    items, total = service.list_cases(page=1, size=10000)
    return {"module": "insure", "total": total, "items": items}


@router.get("/{case_id}", response_model=dict)
def get_case(case_id: int) -> dict:
    """读取单个案件明细（含设备定损与操作轨迹）；不存在时给出可读的错误说明。"""
    case = service.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"保险案件 {case_id} 不存在或已归档")
    return case


@router.post("", response_model=ActionResult)
def create_case(payload: EntryPayload) -> ActionResult:
    """登记出险报案：一次事故的多台设备合并为一案，缺字段时说明原因而不是静默丢弃。"""
    case, message = service.create_case(payload.values)
    if case is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=case)


@router.post("/{case_id}/actions", response_model=ActionResult)
def run_case_action(case_id: int, payload: EntryPayload) -> ActionResult:
    """案件级动作：转入定损、提交理赔、结案；已结案的案件会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    case, message = service.run_action(case_id, action, payload.values)
    if case is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=case)


@router.post("/{case_id}/items/{item_id}/actions", response_model=ActionResult)
def run_item_action(case_id: int, item_id: int, payload: EntryPayload) -> ActionResult:
    """设备级动作：逐台定损或拒赔；一台被拒赔只影响那一台，同案其余设备照常流转。"""
    action = str(payload.values.get("action") or "").strip()
    if action == "定损":
        case, message = service.assess_item(case_id, item_id, payload.values)
    elif action == "拒赔":
        case, message = service.reject_item(case_id, item_id, payload.values)
    else:
        case, message = None, f"动作「{action}」不属于设备定损可执行范围（支持：定损、拒赔）"
    if case is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=case)
