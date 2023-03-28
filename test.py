from dataclasses import dataclass, field


@dataclass(slots=True)
class Ob:
    x: int = field(init=False)


o = Ob()
print(o)
