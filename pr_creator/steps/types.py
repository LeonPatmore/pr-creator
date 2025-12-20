from __future__ import annotations

from dataclasses import dataclass

from ..state import WorkflowState


class BaseNode:
    async def run(self, ctx: GraphRunContext):
        raise NotImplementedError


class End(BaseNode):
    async def run(self, ctx: GraphRunContext):
        return None


@dataclass
class GraphRunContext:
    state: WorkflowState

