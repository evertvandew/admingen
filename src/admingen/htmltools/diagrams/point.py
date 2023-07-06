
from dataclasses import dataclass
import math

@dataclass
class Point:
    x: float
    y: float
    def __str__(self):
        return f"({self.x}, {self.y})"
    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)
    def __sub__(self, other):
        return Point(self.x - other.x, self.y - other.y)
    def __truediv__(self, scalar):
        return Point(self.x/scalar, self.y/scalar)
    def __mul__(self, scalar):
        return Point(self.x*scalar, self.y*scalar)
    def __rmul__(self, scalar):
        return Point(self.x * scalar, self.y * scalar)
    def __len__(self):
        return math.sqrt(self.x*self.x + self.y*self.y)
    def dot(self, other):
        return self.x*other.x + self.y*other.y
    def astuple(self):
        return (int(self.x), int(self.y))
    def transpose(self):
        return Point(x=self.y, y=-self.x)

