"""The local privacy preference is available outside the Screen lifecycle."""

from fastapi import APIRouter

from argus.config import Config
from argus.db import read_offline_private, write_offline_private
from argus.settings import PrivateBody, private_status


def offline_screen_privacy(data_dir):
    path = Config(data_dir=data_dir).db_path
    router = APIRouter()

    @router.get("/screen/api/private")
    def get_private():
        return private_status(read_offline_private(path))

    @router.post("/screen/api/private")
    def set_private(body: PrivateBody | None = None):
        choice = write_offline_private(path, body.private if body else None)
        return {"ok": True, **private_status(choice)}

    return router
