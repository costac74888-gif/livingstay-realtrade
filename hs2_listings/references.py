"""Use the original actor-owned confirmation workflow, never client candidates."""
from hs2_design.domain import ContractError
from hs2_registration.service import RegistrationError


class ReferenceAdapter:
    def __init__(self, service):
        self.service = service

    def verify(self, who, workflow):
        try:
            view = self.service.read(who["user_id"], workflow)
        except RegistrationError:
            raise ContractError("OWNED_CONFIRMED_REFERENCE_REQUIRED") from None
        if view.get("status") != "REFERENCE_CONFIRMED":
            raise ContractError("OWNED_CONFIRMED_REFERENCE_REQUIRED")
        return view

    def list(self, who):
        result = []
        with self.service.lock:
            keys = [k for k, s in self.service.sessions.items() if s["actor"] == who["user_id"]]
            for key in keys:
                try:
                    view = self.verify(who, key)
                except ContractError:
                    continue
                building = view["building"]
                result.append(dict(workflow_id=key, label=building["building_use"] + " · 확인 완료",
                                   building_use=building["building_use"]))
        return result
