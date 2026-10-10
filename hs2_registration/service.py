"""Actor-private, expiring, server-owned address/building/coordinate workflow."""
from copy import deepcopy
import threading
import time
from uuid import uuid4

from .providers import LookupError, exact_legacy, parse_addresses, parse_buildings, parse_coordinates


class RegistrationError(ValueError):
    pass


class RegistrationService:
    def __init__(self, ports, store, clock=time.monotonic, ttl=900, max_sessions=500):
        self.ports,self.store,self.clock,self.ttl,self.max_sessions=ports,store,clock,ttl,max_sessions
        self.sessions={};self.lock=threading.RLock()

    @staticmethod
    def actor(actor):
        if type(actor) is not int or actor<=0:raise RegistrationError("AUTH_REQUIRED")

    def _session(self, actor, key):
        self.actor(actor)
        s=self.sessions.get(key)
        if not s or s["actor"]!=actor:raise RegistrationError("WORKFLOW_NOT_FOUND")
        if self.clock()-s["created"]>=self.ttl:
            del self.sessions[key]
            raise RegistrationError("WORKFLOW_EXPIRED")
        return s

    @staticmethod
    def view(s):
        # Private authenticated response only. Do not pass actor/raw provider payloads.
        keys=("workflow_id","status","addresses","buildings","address","building",
              "coordinates","legacy_state","reference_id","error")
        return deepcopy({k:s[k] for k in keys if k in s})

    @staticmethod
    def attempt(s, call, fallback):
        try:
            value=call()
            s.pop("error",None)
            return value
        except LookupError as e:
            s.update(status=str(e),error=str(e))
        except Exception:
            # Never expose raw errors/URLs/keys supplied by a provider.
            s.update(status=fallback,error=fallback)
        return None

    def start(self, actor, query):
        self.actor(actor)
        if not isinstance(query,str) or not 2<=len(query.strip())<=160 or any(ord(c)<32 for c in query):
            raise RegistrationError("INVALID_ADDRESS_INPUT")
        with self.lock:
            now=self.clock()
            self.sessions={k:s for k,s in self.sessions.items() if now-s["created"]<self.ttl}
            if len(self.sessions)>=self.max_sessions:raise RegistrationError("WORKFLOW_CAPACITY")
            key=str(uuid4())
            s=dict(workflow_id=key,actor=actor,created=now,status="ADDRESS_LOOKUP",addresses=[],buildings=[])
            self.sessions[key]=s
            rows=self.attempt(s,lambda:parse_addresses(self.ports.addresses(query.strip())),"ADDRESS_PROVIDER_FAILED")
            if rows is not None:
                s.update(addresses=rows,status="ADDRESS_SELECTION_REQUIRED" if rows else "ADDRESS_NOT_FOUND")
            return self.view(s)

    def read(self, actor, key):
        with self.lock:return self.view(self._session(actor,key))

    def select_address(self, actor, key, address_id):
        with self.lock:
            s=self._session(actor,key)
            if "reference_id" in s:raise RegistrationError("REFERENCE_ALREADY_CONFIRMED")
            matches=[x for x in s["addresses"] if x["address_key"]==address_id]
            if len(matches)!=1:raise RegistrationError("ADDRESS_SELECTION_INVALID")
            for k in ("building","coordinates","legacy_state","legacy_id","error"):
                s.pop(k,None)
            s.update(address=matches[0],buildings=[],status="REGISTRY_LOOKUP")
            rows=self.attempt(s,lambda:parse_buildings(self.ports.buildings(s["address"]),s["address"]),
                              "REGISTRY_PROVIDER_FAILED")
            if rows is not None:s.update(buildings=rows,status="BUILDING_SELECTION_REQUIRED" if rows else "REGISTRY_UNCONFIRMED")
            return self.view(s)

    def select_building(self, actor, key, building_id):
        with self.lock:
            s=self._session(actor,key)
            if "reference_id" in s:raise RegistrationError("REFERENCE_ALREADY_CONFIRMED")
            matches=[x for x in s["buildings"] if x["building_key"]==building_id]
            if len(matches)!=1:raise RegistrationError("BUILDING_SELECTION_INVALID")
            for k in ("coordinates","legacy_id","legacy_state","error"):
                s.pop(k,None)
            s.update(building=matches[0],status="COORDINATES_REQUIRED")
            return self.view(s)

    def coordinates(self, actor, key):
        with self.lock:
            s=self._session(actor,key)
            if "reference_id" in s:return self.view(s)
            if "building" not in s:raise RegistrationError("BUILDING_REQUIRED")
            for k in ("coordinates","legacy_id","legacy_state","error"):s.pop(k,None)
            coordinate=self.attempt(s,lambda:parse_coordinates(
                self.ports.coordinates(s["address"]),s["address"]),"COORDINATES_PROVIDER_FAILED")
            if coordinate is None:return self.view(s)
            # Keep geometry private even when legacy lookup fails.
            s["coordinates"]=coordinate
            def link():
                return exact_legacy(self.ports.legacy(s["building"]["identity_key"]),s["building"]["identity_key"])
            try:
                legacy=link()
                s.update(legacy_id=legacy,legacy_state="EXACT_EXISTING" if legacy is not None else "SEPARATE_REFERENCE",
                         status="READY_FOR_REFERENCE")
            except LookupError as e:s.update(status=str(e),error=str(e))
            except Exception:s.update(status="MASTER_LOOKUP_FAILED",error="MASTER_LOOKUP_FAILED")
            return self.view(s)

    def confirm(self, actor, key):
        with self.lock:
            s=self._session(actor,key)
            if "reference_id" in s:return self.view(s)  # Idempotent per workflow.
            if s["status"]!="READY_FOR_REFERENCE":raise RegistrationError("REFERENCE_NOT_READY")
            try:
                reference=self.store.save(deepcopy(s["building"]),deepcopy(s["coordinates"]),s["legacy_id"])
            except Exception:
                s.update(status="REFERENCE_SAVE_FAILED",error="REFERENCE_SAVE_FAILED")
                return self.view(s)
            s.update(status="REFERENCE_CONFIRMED",reference_id=str(reference))
            return self.view(s)

    @staticmethod
    def public_view(_private):
        # Reference candidates are not public listings or public map points.
        return {"status":"NOT_PUBLIC","location_precision":"withheld"}
