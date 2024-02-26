from dataclasses import fields, is_dataclass
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Union,
    get_args,
    get_origin,
)

IR = Union[None, bool, int, str, bytes, List["IR"], Dict[str, "IR"]]


class UnstructuringError(Exception):
    pass


def unstructure_list(unstructurer: "Unstructurer", unstructure_as: type, obj: List[Any]) -> IR:
    # TODO: check that get_origin() is a List
    args = get_args(unstructure_as)
    if len(args) > 0:
        return [unstructurer.unstructure_as(args[0], item) for item in obj]
    else:
        # This can happen if we're just give a list of items to unstructure,
        # as opposed to pulling a List[...] annotation out of a dataclass.
        return [unstructurer.unstructure(item) for item in obj]


def unstructure_union(unstructurer: "Unstructurer", unstructure_as: type, obj: Optional[Any]) -> IR:
    args = get_args(unstructure_as)
    for arg in args:
        try:
            return unstructurer.unstructure_as(arg, obj)
        except UnstructuringError:
            continue

    raise UnstructuringError(f"Cannot unstructure as {unstructure_as}")


def unstructure_none(_unstructurer: "Unstructurer", _unstructure_as: type, _obj: None) -> IR:
    return None


class Unstructurer:
    @classmethod
    def with_defaults(
        cls,
        hooks: Mapping[Any, Callable[["Unstructurer", type, Any], IR]],
        field_name_hook: Optional[Callable[[str], str]] = None,
    ) -> "Unstructurer":
        all_hooks: Dict[Any, Callable[["Unstructurer", type, Any], IR]] = {
            list: unstructure_list,
            tuple: unstructure_list,
            Union: unstructure_union,
            type(None): unstructure_none,
        }
        all_hooks.update(hooks)
        return cls(all_hooks, field_name_hook or (lambda x: x))

    def __init__(
        self,
        hooks: Mapping[Any, Callable[["Unstructurer", type, Any], IR]],
        field_name_hook: Callable[[str], str],
    ):
        self._hooks = hooks
        self._field_name_hook = field_name_hook

    def unstructure_as(self, unstructure_as: type, obj: Any) -> IR:
        origin = get_origin(unstructure_as)
        if origin is not None:
            tp = origin
        else:
            tp = unstructure_as

        if tp in self._hooks:
            try:
                return self._hooks[tp](self, unstructure_as, obj)
            except Exception as exc:
                raise UnstructuringError(f"Cannot unstructure as {unstructure_as}") from exc

        if is_dataclass(unstructure_as):
            result = {}
            for field in fields(unstructure_as):
                result_name = self._field_name_hook(field.name)
                result[result_name] = self.unstructure_as(field.type, getattr(obj, field.name))
            return result

        raise UnstructuringError(f"No hooks registered to unstructure {unstructure_as}")

    def unstructure(self, obj: Any) -> IR:
        return self.unstructure_as(type(obj), obj)
