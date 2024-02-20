from dataclasses import fields, is_dataclass


class UnstructuringError(Exception):
    pass


def unstructure_list(unstructurer: "Unstructurer", obj):
    return [unstructurer.unstructure(item) for item in obj]


def unstructure_none(_unstructurer: "Unstructurer", _obj):
    return None


class Unstructurer:
    @classmethod
    def with_defaults(cls, hooks, field_name_hook=None):
        all_hooks = {
            list: unstructure_list,
            tuple: unstructure_list,
            type(None): unstructure_none,
        }
        all_hooks.update(hooks)
        return cls(all_hooks, field_name_hook or (lambda x: x))

    def __init__(self, hooks, field_name_hook):
        self._hooks = hooks
        self._field_name_hook = field_name_hook

    def unstructure(self, obj):
        if is_dataclass(obj):
            result = {}
            for field in fields(obj):
                result_name = self._field_name_hook(field.name)
                result[result_name] = self.unstructure(getattr(obj, field.name))
            return result

        if type(obj) in self._hooks:
            return self._hooks[type(obj)](self, obj)

        raise UnstructuringError(f"No hooks registered to unstructure {type(obj)}")
