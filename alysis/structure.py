import typing
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Any, Iterable, List, Mapping, NewType, Optional, Tuple, Type, TypeVar, Union

from exceptiongroup import ExceptionGroup


def structure_none(val: Any) -> None:
    if val is None:
        return None
    raise Exception(f"The value is not `None`")


def structure_union(structure, path, args: Tuple[Any, ...], val: Any) -> Any:
    exceptions = []
    for arg in args:
        try:
            result = structure(path, arg, val)
            break
        except (StructuringError, StructuringErrorGroup) as exc:
            exceptions.append(exc)
    else:
        print("raising from", path)
        raise StructuringErrorGroup(path, f"Could not structure into any of {args}", exceptions)

    return result


def structure_tuple(structure, path, args: Tuple[Any, ...], val: Any) -> Any:
    # Tuple[()] is supposed to represent an empty tuple. Mypy knows this,
    # but in Python < 3.11 `get_args(Tuple[()])` returns `((),)` instead of `()` as it should.
    # Fixing it here.
    if args == ((),):
        args = ()

    if not isinstance(val, (list, tuple)):
        raise Exception("Can only structure a tuple or a list into a tuple generic")
    if len(val) < len(args):
        raise Exception(
            f"Not enough elements to structure into a tuple: got {len(val)}, need {len(args)}"
        )
    if len(val) > len(args):
        raise Exception(
            f"Too many elements to structure into a tuple: got {len(val)}, need {len(args)}"
        )

    results = []
    exceptions = []
    for index, (item, tp) in enumerate(zip(val, args)):
        try:
            results.append(structure(path + [index], tp, item))
        except (StructuringError, StructuringErrorGroup) as exc:
            exceptions.append(exc)

    if exceptions:
        raise StructuringErrorGroup(path, f"Could not structure into a tuple {args}", exceptions)

    return tuple(results)


def structure_list(structure, path, args: Tuple[Any, ...], val: Any) -> Any:
    if not isinstance(val, (list, tuple)):
        raise Exception("Can only structure a tuple or a list into a list generic")
    return [structure(path + [index], args[0], item) for (index, item) in enumerate(val)]


class StructuringError(Exception):
    @classmethod
    def wrap(cls, path, structure_into, exc):
        return cls(path, f"Failed to structure into {structure_into}: {exc}")

    def __init__(self, path, msg):
        super().__init__(msg)
        self.path = path

    def path_str(self):
        return ".".join(str(item) for item in self.path) if self.path else "<root>"

    def __str__(self):
        return f"Failed to structure at `{self.path_str()}`: {self.args[0]}"


def collect_messages(level, exc):
    if isinstance(exc, StructuringError):
        exceptions = []
        message = exc.args[0]
    else:
        exceptions = exc.exceptions
        message = exc.message

    return [(level, exc.path_str(), message)] + sum(
        (collect_messages(level + 1, exc) for exc in exceptions), []
    )


class StructuringErrorGroup(ExceptionGroup):
    @classmethod
    def wrap(cls, path, structure_into, excs):
        return cls(path, f"Failed to structure into {structure_into}", excs)

    def __new__(cls, path, msg, excs):
        self = super().__new__(StructuringErrorGroup, msg, excs)
        self.path = path
        return self

    def path_str(self):
        return ".".join(str(item) for item in self.path) if self.path else "<root>"

    def __str__(self):
        messages = collect_messages(0, self)

        s = "Failed to structure:"
        for level, path, msg in messages:
            s += "\n" + " " * (level + 1) * 2 + f"{path}: {msg}"

        return s


_T = TypeVar("_T")


class Structurer:
    @classmethod
    def with_defaults(cls, hooks, field_name_hook=None):
        all_hooks = {type(None): structure_none}
        all_hooks.update(hooks)

        return cls(
            all_hooks,
            {
                list: structure_list,
                tuple: structure_tuple,
                Tuple: structure_tuple,
                Union: structure_union,
                UnionType: structure_union,
            },
            field_name_hook or (lambda x: x),
        )

    def __init__(self, hooks, generic_hooks, field_name_hook):
        self._generic_hooks = generic_hooks
        self._hooks = hooks
        self._field_name_hook = field_name_hook

    def _structure_struct_from_dict(self, path, structure_into, obj):
        results = {}
        exceptions = []

        for field in fields(structure_into):
            obj_name = self._field_name_hook(field.name)
            if obj_name in obj:
                try:
                    results[field.name] = self._structure(
                        path + [field.name], field.type, obj[obj_name]
                    )
                except StructuringError as exc:
                    exceptions.append(exc)
            elif field.default is not MISSING:
                results[field.name] = field.default
            else:
                if obj_name == field.name:
                    message = f"Missing field {field.name}"
                else:
                    message = f"Missing field {field.name} ({obj_name} in the input)"
                exceptions.append(StructuringError(path, message))

        if exceptions:
            raise StructuringErrorGroup.wrap(path, structure_into, exceptions)

        return results

    def _structure_struct_from_list(self, path, structure_into, obj):
        results = {}
        exceptions = []

        struct_fields = fields(structure_into)

        if len(obj) > len(struct_fields):
            raise StructuringError(path, f"Too many fields to serialize into {structure_into}")

        for i, field in enumerate(struct_fields):
            if i < len(obj):
                try:
                    results[field.name] = self._structure(path + [field.name], field.type, obj[i])
                except StructuringError as exc:
                    exceptions.append(exc)
            else:
                if field.default is not MISSING:
                    results[field.name] = field.default
                else:
                    exceptions.append(
                        StructuringError(path, f"Missing positional argument {field.name}")
                    )

        if exceptions:
            raise StructuringErrorGroup.wrap(path, structure_into, exceptions)

        return results

    def _structure(self, path, structure_into: Type[_T], obj: Any) -> _T:
        if structure_into in self._hooks:
            hook = self._hooks[structure_into]
            try:
                return hook(obj)
            except Exception as exc:
                raise StructuringError.wrap(path, structure_into, exc) from exc

        if is_dataclass(structure_into):
            if isinstance(obj, dict):
                results = self._structure_struct_from_dict(path, structure_into, obj)
            elif isinstance(obj, (list, tuple)):
                results = self._structure_struct_from_list(path, structure_into, obj)
            else:
                raise StructuringError(
                    path, f"Cannot structure into {structure_into} from {type(obj)}"
                )
            return structure_into(**results)

        origin = typing.get_origin(structure_into)
        if origin is not None and origin in self._generic_hooks:
            args = typing.get_args(structure_into)
            hook = self._generic_hooks[origin]
            try:
                return hook(self._structure, path, args, obj)
            except (StructuringError, StructuringErrorGroup):
                raise
            except Exception as exc:
                raise StructuringError.wrap(path, structure_into, exc) from exc

        raise StructuringError(path, f"No hooks registered to structure into {structure_into}")

    def structure(self, structure_into: Type[_T], obj: Any) -> _T:
        return self._structure([], structure_into, obj)
