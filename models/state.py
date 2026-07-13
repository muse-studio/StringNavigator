from dataclasses import dataclass

@dataclass(frozen=True)
class State:
    sp: int
    fn: int
    hp: int
    fi: tuple

@dataclass(frozen=True)
class MusicState:
    states: tuple

    def is_single(self):
        return len(self.states) == 1
    
    def is_double(self):
        return len(self.states) == 2
