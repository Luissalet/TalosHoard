"""Transcription bench: cases, start a run, poll it, the last saved result."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..bench import case_names, load_case, load_thresholds
from .deps import services

router = APIRouter(prefix="/api/bench")


class BenchBody(BaseModel):
    cases: list[str] | None = Field(None, max_length=8)
    language: str = Field("auto", max_length=12)


@router.get("")
def overview(request: Request):
    svc = services(request)
    return {"cases": [{"name": n, "about": load_case(n).about} for n in case_names()], "thresholds": load_thresholds(),
            "running": svc.bench.running(), "last": svc.bench.last(), "engine": svc.transcriber.info()}


@router.post("", status_code=202)
def start(request: Request, body: BenchBody | None = None):
    body = body or BenchBody()
    svc = services(request)
    running = svc.bench.running()
    if running:
        return running
    try:
        return svc.bench.start(body.cases, body.language)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/{job_id}")
def job(request: Request, job_id: str):
    try:
        return services(request).bench.snapshot(job_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
