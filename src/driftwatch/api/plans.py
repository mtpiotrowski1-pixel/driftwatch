"""Subscription-plan catalog and the pricing algorithm — operator (superadmin)
only.

Instead of typing caps and a price into every organization by hand, the operator
defines plans once here. Assigning a plan to an organization copies its caps onto
it (see ``api.organizations``). Each plan also carries the algorithm's suggested
price so the operator can sanity-check what they charge against what the included
usage actually costs.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.api.deps import (
    InstanceSuperadminUser,
    SecretBoxDep,
    SessionDep,
    SettingsDep,
    require_step_up,
)
from driftwatch.audit import record_audit_event
from driftwatch.billing.plan_contract import lock_plan_contract
from driftwatch.config import Settings
from driftwatch.models import BillingPrice, Plan
from driftwatch.pricing import (
    PricingInputs,
    build_pricing_inputs,
    suggested_price_cents,
)
from driftwatch.schemas import (
    PlanCreate,
    PlanOut,
    PlanUpdate,
    PriceSuggestionOut,
    PricingContextOut,
    PricingUpdate,
    PublicPlanOut,
)
from driftwatch.security.crypto import SecretBox
from driftwatch.settings_store import SettingsStore

router = APIRouter(prefix="/api/plans", tags=["plans"])

_SELF_SERVE_DISABLED_DETAIL = (
    "Self-serve plans are disabled until verified payment activation is available"
)
_BILLING_CONTRACT_FIELDS = frozenset(
    {"key", "max_sites", "max_members", "monthly_ai_check_limit", "currency"}
)
_IMMUTABLE_BILLING_PLAN_DETAIL = (
    "A plan with billing price history has immutable contract fields; "
    "create a new plan version instead"
)


def _store(session: AsyncSession, box: SecretBox) -> SettingsStore:
    # Pricing knobs are platform-wide, so always the instance-default layer.
    return SettingsStore(session, box, org_id=None)


def _to_out(plan: Plan, inputs: PricingInputs) -> PlanOut:
    out = PlanOut.model_validate(plan)
    suggested = suggested_price_cents(plan.max_sites, plan.monthly_ai_check_limit, inputs)
    out.suggested_price_cents = suggested
    out.effective_price_cents = (
        plan.price_override_cents if plan.price_override_cents is not None else suggested
    )
    return out


def _context_out(inputs: PricingInputs) -> PricingContextOut:
    return PricingContextOut(
        base_fee=float(inputs.base_fee),
        per_site_fee=float(inputs.per_site_fee),
        ai_margin=float(inputs.margin),
        unlimited_sites=inputs.unlimited_sites,
        unlimited_checks=inputs.unlimited_checks,
        currency=inputs.currency,
        model=inputs.model,
        input_price_per_1m=float(inputs.input_price_per_1m),
        output_price_per_1m=float(inputs.output_price_per_1m),
        avg_prompt_tokens=inputs.avg_prompt_tokens,
        avg_completion_tokens=inputs.avg_completion_tokens,
        cost_per_check=float(inputs.cost_per_check),
    )


async def _require_unique_key(
    session: AsyncSession, key: str, *, exclude_id: int | None = None
) -> None:
    stmt = select(Plan.id).where(Plan.key == key)
    if exclude_id is not None:
        stmt = stmt.where(Plan.id != exclude_id)
    if (await session.execute(stmt)).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A plan with key '{key}' already exists")


@router.get("", response_model=list[PlanOut])
async def list_plans(
    session: SessionDep, box: SecretBoxDep, _: InstanceSuperadminUser
) -> list[PlanOut]:
    inputs = await build_pricing_inputs(session, _store(session, box))
    plans = (await session.execute(select(Plan).order_by(Plan.sort_order, Plan.name))).scalars()
    return [_to_out(plan, inputs) for plan in plans]


@router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanCreate,
    request: Request,
    session: SessionDep,
    box: SecretBoxDep,
    settings: SettingsDep,
    admin: InstanceSuperadminUser,
) -> PlanOut:
    await require_step_up(request, admin, settings)
    _reject_self_serve(payload.is_self_serve, settings)
    await _require_unique_key(session, payload.key)
    plan = Plan(**payload.model_dump())
    session.add(plan)
    await session.flush()
    record_audit_event(
        session,
        request,
        admin,
        action="plan.created",
        target_type="plan",
        target_id=plan.id,
        target_label=plan.name,
        organization_id=None,
        details={
            "key": plan.key,
            "max_sites": plan.max_sites,
            "max_members": plan.max_members,
            "monthly_ai_check_limit": plan.monthly_ai_check_limit,
            "price_override_cents": plan.price_override_cents,
            "currency": plan.currency,
            "is_active": plan.is_active,
        },
    )
    inputs = await build_pricing_inputs(session, _store(session, box))
    return _to_out(plan, inputs)


@router.get("/public", response_model=list[PublicPlanOut])
async def list_public_plans(session: SessionDep, settings: SettingsDep) -> list[PublicPlanOut]:
    if not settings.billing_self_serve_ready:
        return []
    rows = (
        await session.execute(
            select(Plan, BillingPrice)
            .join(BillingPrice, BillingPrice.plan_id == Plan.id)
            .where(
                Plan.is_active.is_(True),
                Plan.is_self_serve.is_(True),
                BillingPrice.provider == settings.billing_provider,
                BillingPrice.is_active.is_(True),
            )
            .order_by(Plan.sort_order, Plan.name, BillingPrice.version.desc())
        )
    ).all()
    result: list[PublicPlanOut] = []
    seen: set[int] = set()
    for plan, price in rows:
        if plan.id in seen:
            continue
        seen.add(plan.id)
        result.append(
            PublicPlanOut(
                key=plan.key,
                name=plan.name,
                max_sites=plan.max_sites,
                max_members=plan.max_members,
                monthly_ai_check_limit=plan.monthly_ai_check_limit,
                price_cents=price.unit_amount_minor,
                currency=price.currency,
            )
        )
    return result


@router.get("/pricing", response_model=PricingContextOut)
async def get_pricing(
    session: SessionDep, box: SecretBoxDep, _: InstanceSuperadminUser
) -> PricingContextOut:
    return _context_out(await build_pricing_inputs(session, _store(session, box)))


@router.put("/pricing", response_model=PricingContextOut)
async def update_pricing(
    payload: PricingUpdate,
    request: Request,
    session: SessionDep,
    box: SecretBoxDep,
    settings: SettingsDep,
    admin: InstanceSuperadminUser,
) -> PricingContextOut:
    await require_step_up(request, admin, settings)
    values = payload.model_dump(exclude_unset=True)
    if values:
        store = _store(session, box)
        await store.set_many(
            {f"pricing_{key}": _as_text(key, value) for key, value in values.items()}
        )
        record_audit_event(
            session,
            request,
            admin,
            action="pricing.updated",
            target_type="pricing",
            organization_id=None,
            details={"changed_fields": sorted(values)},
        )
    return _context_out(await build_pricing_inputs(session, _store(session, box)))


@router.get("/suggest", response_model=PriceSuggestionOut)
async def suggest_price(
    session: SessionDep,
    box: SecretBoxDep,
    _: InstanceSuperadminUser,
    max_sites: int | None = Query(default=None, ge=0),
    monthly_ai_check_limit: int | None = Query(default=None, ge=0),
) -> PriceSuggestionOut:
    inputs = await build_pricing_inputs(session, _store(session, box))
    return PriceSuggestionOut(
        suggested_price_cents=suggested_price_cents(max_sites, monthly_ai_check_limit, inputs),
        currency=inputs.currency,
    )


@router.patch("/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    request: Request,
    session: SessionDep,
    box: SecretBoxDep,
    settings: SettingsDep,
    admin: InstanceSuperadminUser,
) -> PlanOut:
    await require_step_up(request, admin, settings)
    plan = await _require_plan(session, plan_id, lock_contract=True)
    data = payload.model_dump(exclude_unset=True)
    before = {field: getattr(plan, field) for field in data}
    _reject_self_serve(data.get("is_self_serve"), settings)
    changed_contract_fields = {
        field
        for field in data.keys() & _BILLING_CONTRACT_FIELDS
        if data[field] != getattr(plan, field)
    }
    if changed_contract_fields and await _has_billing_price_history(session, plan.id):
        raise HTTPException(status.HTTP_409_CONFLICT, _IMMUTABLE_BILLING_PLAN_DETAIL)
    if "key" in data and data["key"] != plan.key:
        await _require_unique_key(session, data["key"], exclude_id=plan.id)
    for key, value in data.items():
        setattr(plan, key, value)
    changes = {
        field: {"from": before[field], "to": getattr(plan, field)}
        for field in before
        if before[field] != getattr(plan, field)
    }
    if changes:
        record_audit_event(
            session,
            request,
            admin,
            action="plan.updated",
            target_type="plan",
            target_id=plan.id,
            target_label=plan.name,
            organization_id=None,
            details={"changes": changes},
        )
    inputs = await build_pricing_inputs(session, _store(session, box))
    return _to_out(plan, inputs)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: int,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    admin: InstanceSuperadminUser,
) -> None:
    await require_step_up(request, admin, settings)
    # Organizations on this plan keep their copied caps; their plan link is
    # cleared by the foreign key's ON DELETE SET NULL.
    plan = await _require_plan(session, plan_id, lock_contract=True)
    if await _has_billing_price_history(session, plan.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A plan with billing price history must be archived; create a new plan version "
            "for different contract terms",
        )
    record_audit_event(
        session,
        request,
        admin,
        action="plan.deleted",
        target_type="plan",
        target_id=plan.id,
        target_label=plan.name,
        organization_id=None,
        details={"key": plan.key},
    )
    await session.delete(plan)


async def _require_plan(
    session: AsyncSession, plan_id: int, *, lock_contract: bool = False
) -> Plan:
    plan = (
        await lock_plan_contract(session, plan_id)
        if lock_contract
        else await session.get(Plan, plan_id)
    )
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plan {plan_id} not found")
    return plan


async def _has_billing_price_history(session: AsyncSession, plan_id: int) -> bool:
    row = await session.execute(
        select(BillingPrice.id).where(BillingPrice.plan_id == plan_id).limit(1)
    )
    return row.first() is not None


def _reject_self_serve(value: object, settings: Settings) -> None:
    if value is True and not settings.billing_self_serve_ready:
        raise HTTPException(status.HTTP_409_CONFLICT, _SELF_SERVE_DISABLED_DETAIL)


def _as_text(key: str, value: object) -> str:
    if key == "currency":
        return str(value).upper()
    return str(value)
