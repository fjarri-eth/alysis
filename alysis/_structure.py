import typing
from dataclasses import MISSING, fields, is_dataclass
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    get_args,
)

# TODO (PY): added to the standard library in 3.11
from exceptiongroup import ExceptionGroup

Path = List[Union[str, int]]


def structure_none(_structurer: "Structurer", _structure_into: type, _path: Path, val: Any) -> None:
    if val is not None:
        raise ValueError("The value is not `None`")


def structure_union(structurer: "Structurer", structure_into: type, path: Path, val: Any) -> Any:
    exceptions = []
    args = get_args(structure_into)
    for arg in args:
        try:
            result = structurer.structure_at_path(path, arg, val)
            break
        except (StructuringError, StructuringErrorGroup) as exc:
            exceptions.append(exc)
    else:
        raise StructuringErrorGroup(path, f"Could not structure into any of {args}", exceptions)

    return result


def structure_tuple(structurer: "Structurer", structure_into: type, path: Path, val: Any) -> Any:
    args = get_args(structure_into)

    # Tuple[()] is supposed to represent an empty tuple. Mypy knows this,
    # but in Python < 3.11 `get_args(Tuple[()])` returns `((),)` instead of `()` as it should.
    # Fixing it here.
    if args == ((),):
        args = ()

    if not isinstance(val, (list, tuple)):
        raise TypeError("Can only structure a tuple or a list into a tuple generic")
    if len(val) < len(args):
        raise ValueError(
            f"Not enough elements to structure into a tuple: got {len(val)}, need {len(args)}"
        )
    if len(val) > len(args):
        raise ValueError(
            f"Too many elements to structure into a tuple: got {len(val)}, need {len(args)}"
        )

    results = []
    exceptions = []
    for index, (item, tp) in enumerate(zip(val, args)):
        try:
            results.append(structurer.structure_at_path([*path, index], tp, item))
        except (StructuringError, StructuringErrorGroup) as exc:  # noqa: PERF203
            exceptions.append(exc)

    if exceptions:
        raise StructuringErrorGroup(path, f"Could not structure into a tuple {args}", exceptions)

    return tuple(results)


def structure_list(structurer: "Structurer", structure_into: type, path: Path, val: Any) -> Any:
    args = get_args(structure_into)
    if not isinstance(val, (list, tuple)):
        raise TypeError("Can only structure a tuple or a list into a list generic")
    return [
        structurer.structure_at_path([*path, index], args[0], item)
        for (index, item) in enumerate(val)
    ]


class StructuringError(Exception):
    @classmethod
    def wrap_exception(
        cls, path: List[Union[int, str]], structure_into: Any, exc: Exception
    ) -> "StructuringError":
        return cls(path, f"Failed to structure into {structure_into}: {exc}")

    def __init__(self, path: List[Union[int, str]], msg: str):
        super().__init__(msg)
        self.path = path

    def path_str(self) -> str:
        return ".".join(str(item) for item in self.path) if self.path else "<root>"

    def __str__(self) -> str:
        return f"Failed to structure at `{self.path_str()}`: {self.args[0]}"


def collect_messages(level: int, exc: StructuringError) -> List[Tuple[int, str, str]]:
    message = exc.args[0]
    exceptions: List[StructuringError]
    if isinstance(exc, StructuringErrorGroup):
        # By construction we will only have those types in the list.
        exceptions = cast(List[StructuringError], exc.exceptions)
    else:
        exceptions = []

    result = [(level, exc.path_str(), message)]
    for exc in exceptions:
        result.extend(collect_messages(level + 1, exc))
    return result


_S = TypeVar("_S", bound="StructuringErrorGroup")


class StructuringErrorGroup(ExceptionGroup[StructuringError], StructuringError):
    @classmethod
    def wrap_exceptions(
        cls: Type[_S],
        path: List[Union[int, str]],
        structure_into: Any,
        excs: Sequence[StructuringError],
    ) -> _S:
        return cls(path, f"Failed to structure into {structure_into}", excs)

    def __new__(
        cls: Type[_S], _path: List[Union[int, str]], msg: str, excs: Sequence[StructuringError]
    ) -> _S:
        # TODO (PY): no need for type-ignore in 3.12.
        return ExceptionGroup.__new__(cls, msg, excs)  # type: ignore[no-any-return]

    def __init__(self, path: List[Union[int, str]], msg: str, excs: Sequence[StructuringError]):
        ExceptionGroup.__init__(self, msg, excs)
        StructuringError.__init__(self, path, msg)

    def __str__(self) -> str:
        messages = collect_messages(0, self)

        s = "Failed to structure:"
        for level, path, msg in messages:
            s += "\n" + " " * (level + 1) * 2 + f"{path}: {msg}"

        return s


_T = TypeVar("_T")


class Structurer:
    @classmethod
    def with_defaults(
        cls,
        hooks: Mapping[Any, Callable[["Structurer", type, Path, Any], Any]],
        field_name_hook: Optional[Callable[[str], str]] = None,
    ) -> "Structurer":
        all_hooks: Dict[Any, Callable[["Structurer", type, Path, Any], Any]] = {
            type(None): structure_none,
            list: structure_list,
            tuple: structure_tuple,
            Tuple: structure_tuple,
            Union: structure_union,
        }
        all_hooks.update(hooks)

        return cls(
            all_hooks,
            field_name_hook or (lambda x: x),
        )

    def __init__(
        self,
        hooks: Mapping[Any, Callable[["Structurer", type, Path, Any], Any]],
        field_name_hook: Callable[[str], str],
    ):
        self._hooks = hooks
        self._field_name_hook = field_name_hook

    def _structure_struct_from_dict(
        self, path: Path, structure_into: type, obj: Any
    ) -> Dict[str, Any]:
        results = {}
        exceptions = []

        for field in fields(structure_into):
            obj_name = self._field_name_hook(field.name)
            if obj_name in obj:
                try:
                    results[field.name] = self.structure_at_path(
                        [*path, field.name], field.type, obj[obj_name]
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
            raise StructuringErrorGroup.wrap_exceptions(path, structure_into, exceptions)

        return results

    def _structure_struct_from_list(
        self, path: Path, structure_into: type, obj: Any
    ) -> Dict[str, Any]:
        results = {}
        exceptions = []

        struct_fields = fields(structure_into)

        if len(obj) > len(struct_fields):
            raise StructuringError(path, f"Too many fields to serialize into {structure_into}")

        for i, field in enumerate(struct_fields):
            if i < len(obj):
                try:
                    results[field.name] = self.structure_at_path(
                        [*path, field.name], field.type, obj[i]
                    )
                except StructuringError as exc:
                    exceptions.append(exc)
            elif field.default is not MISSING:
                results[field.name] = field.default
            else:
                exceptions.append(
                    StructuringError(path, f"Missing positional argument {field.name}")
                )

        if exceptions:
            raise StructuringErrorGroup.wrap_exceptions(path, structure_into, exceptions)

        return results

    def structure_at_path(self, path: Path, structure_into: Type[_T], obj: Any) -> _T:
        origin = typing.get_origin(structure_into)
        if origin is not None:
            tp = origin
        else:
            tp = structure_into

        if tp in self._hooks:
            hook = self._hooks[tp]
            try:
                # Python typing is not advanced enough to enforce it,
                # so we are relying on the hook returning the type it was assigned to.
                return cast(_T, hook(self, structure_into, path, obj))
            except Exception as exc:  # noqa: BLE001
                raise StructuringError.wrap_exception(path, structure_into, exc) from exc

        if is_dataclass(structure_into):
            if isinstance(obj, dict):
                results = self._structure_struct_from_dict(path, structure_into, obj)
            elif isinstance(obj, (list, tuple)):
                results = self._structure_struct_from_list(path, structure_into, obj)
            else:
                raise StructuringError(
                    path, f"Cannot structure into {structure_into} from {type(obj)}"
                )

            # Python typing is not advanced enough to enforce it,
            # so we are relying on the hook returning the type it was assigned to.
            return cast(_T, structure_into(**results))

        raise StructuringError(path, f"No hooks registered to structure into {structure_into}")

    def structure(self, structure_into: Type[_T], obj: Any) -> _T:
        return self.structure_at_path([], structure_into, obj)
