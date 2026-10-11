"""Inspect executable production wiring, not the presence of development files.

No provider is invoked here. Run through hs2_production_preflight.py, which owns
the DB and blocks network access before importing the production entrypoint.
"""
import functools
import inspect
from pathlib import Path
import types
from werkzeug.local import LocalProxy


class BoundaryError(RuntimeError):
    pass


def forbidden(value):
    module = getattr(value, "__module__", type(value).__module__) or ""
    name = getattr(value, "__name__", type(value).__name__)
    return (
        module.startswith("hs2_")
        and (".fixtures" in module or ".fixture_http" in module
             or name in {"connect_fixture", "require_fixture", "OwnedSandbox"})
    )


def reject_fixture_call(frame, event, arg):
    """Catch factories even if the resulting app/repository is later discarded."""
    if event == "call":
        module = frame.f_globals.get("__name__", "")
        name = frame.f_code.co_name
        if (name != "<module>" and module.startswith("hs2_") and (
                ".fixtures" in module or ".fixture_http" in module
                or name in {"connect_fixture", "require_fixture"}
                or (module == "hs2_finance.adapter" and name == "__init__"))):
            raise BoundaryError("PRODUCTION_FIXTURE_FACTORY")


ROLE_PORTS = {
    "current_consumer", "current_operator", "resolve_admin", "consumer_for",
    "current_actor", "actor_for",
}


def inspect_app(app, root):
    """Walk only objects reachable from the registered WSGI application.

    Unused imports, files and unregistered blueprints are intentionally not
    roots. Follow closures/defaults, referenced globals and repository fields,
    so aliasing a fixture callable does not turn it into production code.
    """
    root = Path(root).resolve()
    source_root = Path(__file__).resolve().parents[1]
    def local_file(filename):
        path = Path(filename).resolve()
        return any(path.is_relative_to(p) and not any(
            part.startswith(".") or part == "node_modules"
            for part in path.relative_to(p).parts
        ) for p in (root, source_root))
    # Keep strong references: temporary dictionaries can otherwise be freed
    # and their IDs reused, silently skipping a later service/resolver.
    seen = {}
    roles_seen = {}

    def role(value):
        if not callable(value) or id(value) in roles_seen:
            return
        roles_seen[id(value)] = value
        # The trusted resolver must not synthesize an identity for an anonymous
        # request, including a request carrying only development session flags.
        for flags in ({}, {"fixture_admin": True, "fixture_consumer": True,
                           "fixture_operator": True}):
            with app.test_request_context("/"):
                from flask import session
                session.update(flags)
                signature = inspect.signature(value)
                try:
                    signature.bind()
                    args = ()
                except TypeError:
                    # A user-keyed port must not manufacture an actor when no
                    # authenticated user key exists. Do not swallow TypeError
                    # raised *inside* a resolver.
                    signature.bind(None)
                    args = (None,)
                result = value(*args)
                if result is not None:
                    raise BoundaryError("PRODUCTION_DEFAULT_ACTOR")

    def walk(value, edge=""):
        # Request/session proxies are resolved only by the anonymous role probe,
        # not by attribute inspection outside a request.
        if issubclass(type(value), LocalProxy):
            return
        if edge in ROLE_PORTS:
            role(value)
        if id(value) in seen:
            return
        seen[id(value)] = value
        if forbidden(value):
            raise BoundaryError("PRODUCTION_FIXTURE_REFERENCE")
        if edge in {"provider", "payment_provider"} and getattr(value, "sandbox", False) is True:
            raise BoundaryError("PRODUCTION_SANDBOX_PROVIDER")
        if isinstance(value, functools.partial):
            walk(value.func)
            walk(value.args)
            walk(value.keywords)
        elif isinstance(value, types.MethodType):
            walk(value.__func__)
            walk(value.__self__)
        elif isinstance(value, types.FunctionType):
            walk(getattr(value, "__wrapped__", None))
            filename = Path(value.__code__.co_filename)
            if not local_file(filename):
                return
            walk(value.__defaults__)
            walk(value.__kwdefaults__)
            for name, cell in zip(value.__code__.co_freevars, value.__closure__ or ()):
                try:
                    child = cell.cell_contents
                except ValueError:
                    continue
                walk(child, name)
            # co_names also contains attribute names: inspect only attributes
            # actually named by this function, not every imported module.
            for name in value.__code__.co_names:
                child = value.__globals__.get(name)
                if isinstance(child, types.ModuleType):
                    for attr in value.__code__.co_names:
                        if attr in vars(child):
                            walk(vars(child)[attr], attr)
                else:
                    walk(child, name)
        elif isinstance(value, dict):
            for name, child in value.items():
                walk(child, str(name))
        elif isinstance(value, (list, tuple, set)):
            for child in value:
                walk(child)
        elif not isinstance(value, (str, bytes, int, float, bool, type(None), types.ModuleType)):
            module = inspect.getmodule(type(value))
            filename = getattr(module, "__file__", None)
            local = filename and local_file(filename)
            if local:
                if getattr(value, "sandbox", False) is True:
                    raise BoundaryError("PRODUCTION_SANDBOX_PROVIDER")
                walk(vars(value) if hasattr(value, "__dict__") else {})
                for name, method in vars(type(value)).items():
                    if isinstance(method, types.FunctionType):
                        walk(method, name)

    # Flask internals are not walked indiscriminately. These are its executable
    # registration boundaries plus explicitly attached application services.
    for name in ("view_functions", "before_request_funcs", "after_request_funcs",
                 "teardown_request_funcs", "error_handler_spec", "url_value_preprocessors"):
        walk(getattr(app, name))
    walk(dict(app.config))
    for name, value in vars(app).items():
        if name.startswith("fixture"):
            raise BoundaryError("PRODUCTION_FIXTURE_SERVICE")
        if name not in {"config", "view_functions"}:
            walk(value, name)


def inspect_environment(env, expected_database):
    # The test transport itself owns a legacy socket. HS2 fixture capability
    # must never be selected by the production command being exercised.
    if any(env.get(key) for key in ("HS2_FIXTURE_SOCKET", "HS2_FIXTURE_TEST")):
        raise BoundaryError("PRODUCTION_FIXTURE_DATABASE")
    if env.get("DATABASE_URL") != expected_database:
        raise BoundaryError("PRODUCTION_DATABASE_SELECTION")
    if env.get("SERVE_MINIFIED_ASSETS") != "1" or env.get("SKIP_STARTUP_SCHEMA_INIT") != "1":
        raise BoundaryError("PRODUCTION_START_FLAGS")
